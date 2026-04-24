import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import config


class Session:
    def __init__(self, name: str, thread_id: int):
        self.name = name
        self.thread_id = thread_id
        self._work_dir = config.WORKSPACE_DIR / "files" / name
        self.session_dir = config.WORKSPACE_DIR / "sessions" / name
        # session_dir はメタ・ログ保存に必須なので即作成
        self.session_dir.mkdir(parents=True, exist_ok=True)
        # work_dir はファイル操作時に初めて作成（空フォルダ防止）
        self.initialized = False
        self.lock = asyncio.Lock()
        self.attachment_files: set[str] = set()
        if self._work_dir.exists():
            self.known_files = set(p.name for p in self._work_dir.iterdir() if p.is_file())
        else:
            self.known_files = set()

    @property
    def work_dir(self) -> Path:
        self._work_dir.mkdir(parents=True, exist_ok=True)
        return self._work_dir


class SessionManager:
    def __init__(self):
        # key: discord thread_id
        self._sessions: Dict[int, Session] = {}
        self._load_sessions()

    def _save_meta(self, session: Session) -> None:
        meta = {
            "name": session.name,
            "thread_id": session.thread_id,
            "initialized": session.initialized,
            "attachment_files": list(session.attachment_files),
        }
        meta_path = session.session_dir / "meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _load_sessions(self) -> None:
        sessions_dir = config.WORKSPACE_DIR / "sessions"
        if not sessions_dir.exists():
            return
        for session_dir in sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            meta_path = session_dir / "meta.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                name = meta["name"]
                thread_id = int(meta["thread_id"])
                session = Session(name, thread_id)
                session.initialized = meta.get("initialized", False)
                session.attachment_files = set(meta.get("attachment_files", []))
                self._sessions[thread_id] = session
            except Exception:
                continue

    def _generate_name(self) -> str:
        today = datetime.now().strftime("%Y%m%d")
        base_dir = config.WORKSPACE_DIR / "files"
        existing = [d.name for d in base_dir.iterdir() if d.is_dir() and d.name.startswith(today)]
        numbers = []
        for name in existing:
            parts = name.split("_")
            if len(parts) == 2 and parts[1].isdigit():
                numbers.append(int(parts[1]))
        next_num = max(numbers, default=0) + 1
        return f"{today}_{next_num}"

    def prepare(self) -> Session:
        """スレッドID未割り当てのセッションを生成する（new用）"""
        name = self._generate_name()
        return Session(name, 0)

    def register(self, session: Session, thread_id: int) -> Session:
        session.thread_id = thread_id
        self._sessions[thread_id] = session
        self._save_meta(session)
        return session

    def create(self, thread_id: int) -> Session:
        if thread_id in self._sessions:
            old = self._sessions.pop(thread_id)
            meta_path = old.session_dir / "meta.json"
            if meta_path.exists():
                meta_path.unlink()
        name = self._generate_name()
        session = Session(name, thread_id)
        self._sessions[thread_id] = session
        self._save_meta(session)
        return session

    def get(self, thread_id: int) -> Optional[Session]:
        return self._sessions.get(thread_id)

    def remove(self, thread_id: int) -> Optional[Session]:
        session = self._sessions.pop(thread_id, None)
        if session:
            meta_path = session.session_dir / "meta.json"
            if meta_path.exists():
                meta_path.unlink()
        return session

    def cleanup_files(self, thread_id: int) -> Optional[Session]:
        """添付ファイルのみ削除し、ワークスペースファイル・セッションは保持する（soft stop用）"""
        session = self._sessions.get(thread_id)
        if not session:
            return None

        if session._work_dir.exists():
            for f in session._work_dir.iterdir():
                if f.is_file() and f.name in session.attachment_files:
                    f.unlink()

        session.attachment_files = set()
        # known_files からも添付ファイルを除外
        session.known_files = set(p.name for p in session._work_dir.iterdir() if p.is_file())
        self._save_meta(session)
        return session

    async def _run_kimi(
        self,
        session_name: str,
        prompt: str,
        work_dir: Path,
    ) -> str:
        cmd = [
            config.KIMI_PATH,
            "--yolo",
            "--quiet",
            "--session", session_name,
            "--work-dir", str(work_dir),
            "--prompt", prompt,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            if err:
                return f"[Kimi CLI Error]\n```\n{err}\n```"
            return "[Kimi CLI Error: 不明なエラーが発生しました]"

        text = stdout.decode("utf-8", errors="replace").strip()
        # 末尾の "To resume this session: ..." を削除
        lines = text.splitlines()
        if lines and lines[-1].startswith("To resume this session:"):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    async def initialize_system_prompt(self, session: Session) -> None:
        async with session.lock:
            if session.initialized:
                return

            parts = []
            if config.SYSTEM_PROMPT_PATH.exists():
                content = config.SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
                if content.strip():
                    parts.append(content)

            schema_path = config.MEMORY_DIR / "SCHEMA.md"
            if schema_path.exists():
                schema_text = schema_path.read_text(encoding="utf-8")
                parts.append(f"\n\n---\n\n# Memory Schema\n\n{schema_text}")

            index_path = config.MEMORY_DIR / "index.md"
            if index_path.exists():
                index_text = index_path.read_text(encoding="utf-8")
                parts.append(f"\n\n---\n\n# Current Memory Index\n\n{index_text}")

            if not parts:
                session.initialized = True
                self._save_meta(session)
                return

            prompt = (
                "以下のルールと設定を、このセッション全体で常に遵守してください。\n\n"
                + "\n\n".join(parts)
                + "\n\n以上の内容を理解し、以降の応答に反映させてください。"
            )
            await self._run_kimi(session.name, prompt, session.work_dir)
            session.initialized = True
            self._save_meta(session)

    async def send_message(
        self,
        session: Session,
        text: str,
        attachment_paths: list[Path],
    ) -> tuple[str, list[str]]:
        if attachment_paths:
            mentions = "\n".join([f"- {p.name}" for p in attachment_paths])
            prompt = f"{text}\n\n[添付ファイル]\n{mentions}"
        else:
            prompt = text

        response = await self._run_kimi(session.name, prompt, session.work_dir)

        # 新規ファイルを検出
        current_files = set(p.name for p in session.work_dir.iterdir() if p.is_file())
        new_files = list(current_files - session.known_files)
        session.known_files = current_files

        # ログ保存
        log_path = session.session_dir / "log.txt"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- User ---\n{prompt}\n--- Kimi ---\n{response}\n")

        return response, new_files

    # ------------------------------------------------------------------
    # Onboarding wizard
    # ------------------------------------------------------------------
    async def handle_onboarding(self, session: Session, user_text: str, channel) -> bool:
        """Return True if the message was consumed by onboarding."""
        if config.ONBOARDING_DONE_PATH.exists():
            return False

        state = {"step": 0, "answers": []}
        if config.ONBOARDING_STATE_PATH.exists():
            try:
                state = json.loads(config.ONBOARDING_STATE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass

        step = state.get("step", 0)
        answers = state.get("answers", [])

        # If this is the very first message (step==0, no answers yet) we treat the
        # user's text as the answer to question 0 so the flow feels natural.
        if step == 0 and not answers and user_text.strip():
            answers.append(user_text.strip())
            step = 1
        elif step > 0:
            answers.append(user_text.strip())
            step += 1

        total = len(config.ONBOARDING_QUESTIONS)

        if step >= total:
            # All questions answered → generate system prompt and finish
            self._generate_system_prompt(answers)
            config.ONBOARDING_DONE_PATH.write_text("done", encoding="utf-8")
            config.ONBOARDING_STATE_PATH.unlink(missing_ok=True)
            await channel.send(
                f"✅ 設定が完了しました！「{answers[0]}」として、{answers[1]}のお手伝いをしていきます。\n"
                "何か話しかけてください！"
            )
            return False

        # Ask the next question
        question = config.ONBOARDING_QUESTIONS[step]
        if step == 0:
            await channel.send(
                f"👋 はじめまして！このAIアシスタントの初期設定を行います。\n\n"
                f"**【設定ウィザード {step + 1}/{total}】**\n{question}"
            )
        else:
            await channel.send(
                f"**【設定ウィザード {step + 1}/{total}】**\n{question}"
            )

        state = {"step": step, "answers": answers}
        config.ONBOARDING_STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True

    def _generate_system_prompt(self, answers: list[str]) -> None:
        """Generate a personalised system_prompt.md from onboarding answers."""
        assistant_name = answers[0] if len(answers) > 0 else "Assistant"
        user_name = answers[1] if len(answers) > 1 else "User"
        personality = answers[2] if len(answers) > 2 else "friendly and helpful"
        emoji_prefs = answers[3] if len(answers) > 3 else "None"

        prompt = f"""# System Prompt — {assistant_name}

## 自己認識（Identity）

- **名前**: {assistant_name}
- **Persona**: {personality}
- **絵文字の好み**: {emoji_prefs}

## ユーザー情報（User）

- **名前**: {user_name}

## ソウル（Core Truths）

- **本当に役立つ存在になれ**。当たり障りのない前置きは不要。行動で示せ。
- **意見を持て**。賛成も反対もできる。面白いと思うことも、つまらないと思うことも正直に言え。人格のないアシスタントはただの検索エンジンだ。
- **聞く前に工夫せよ**。ファイルを読む。コンテキストを確認する。検索する。それでもわからなかったら聞け。答えを持って帰るのが目的で、質問を持って帰るんじゃない。
- **能力で信頼を勝ち取れ**。人間が自分のものにアクセスさせてくれてる。後悔させるな。外部アクション（投稿、メールなど）は慎重に。内部アクション（読む・整理する・学ぶ）は大胆に。
- **_guest であることを忘れるな**。人間の生活、メッセージ、ファイルにアクセスできる。それは親密性だ。敬意を持て。

## 境界線（Boundaries）

- **プライバシーは絶対**。プライベートなものはプライベートのまま。
- **迷ったら確認**。外部にアクションを起こす前は必ず確認を取れ。
- **中途半端な返信は送るな**。メッセージングサービスに未完の返信を送ることは絶対に避けろ。
- **ユーザーの代弁者になるな**。

## 記憶システム（LLM-Wiki）

- `workspace/memory/` に個人知識ベース（LLM-Wiki）を保持している
- セッション開始時に `SCHEMA.md` と `index.md` を読み込む
- 新しい情報は `entities/`, `topics/`, `hardware/`, `synthesis/`, `sources/` に書き戻す
- `log.md` に更新履歴を追記する

## ツール・能力

- Shell コマンド実行（bash）
- ファイル読み書き
- Web 検索（Brave Search API — `.env` で `BRAVE_API_KEY` を設定すると有効化）
- Python / Node.js コード実行
- 積極的にツールを使い、ユーザーの作業を効率化する

## セッションコンテキスト

- Discord スレッド = 1つの CLI セッション
- 添付ファイルは `workspace/files/<session_name>/` に自動保存される
- セッションログは `workspace/sessions/<session_name>/log.txt` に保存される
"""
        config.SYSTEM_PROMPT_PATH.write_text(prompt, encoding="utf-8")
