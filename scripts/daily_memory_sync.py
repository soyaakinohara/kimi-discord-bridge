#!/usr/bin/env python3
"""
Daily LLM-Wiki Memory Sync

毎朝実行することで、前日のセッションログとファイルを読み込み、
workspace/memory/ 以下の LLM-Wiki を更新・整理します。

Usage:
    python scripts/daily_memory_sync.py
    python scripts/daily_memory_sync.py --date 20260423
    python scripts/daily_memory_sync.py --workspace /path/to/workspace
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configurable limits
# ---------------------------------------------------------------------------
MAX_LOG_PER_SESSION = 50_000      # 1セッションあたりのログ最大文字数
MAX_TOTAL_LOG_SIZE = 200_000      # 全セッションのログ合計最大文字数
MEMORY_SESSION_NAME = "memory-sync"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_workspace_dir() -> Path:
    """Return the workspace directory."""
    # When run from repo root, workspace is right next to scripts/
    repo_root = Path(__file__).parent.parent.resolve()
    return repo_root / "workspace"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily LLM-Wiki memory sync")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date in YYYYMMDD format (default: yesterday)",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Path to workspace directory (default: ./workspace)",
    )
    return parser.parse_args()


def resolve_target_date(date_str: str | None) -> str:
    if date_str:
        # Validate format
        datetime.strptime(date_str, "%Y%m%d")
        return date_str
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime("%Y%m%d")


def collect_sessions(workspace_dir: Path, target_date: str) -> list[dict]:
    """
    Collect sessions whose name starts with target_date.
    Returns list of dicts with keys: name, log_text, files.
    """
    sessions_dir = workspace_dir / "sessions"
    files_dir = workspace_dir / "files"
    sessions: list[dict] = []

    if not sessions_dir.exists():
        print(f"[WARN] Sessions directory not found: {sessions_dir}")
        return sessions

    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        name = session_dir.name
        if not name.startswith(target_date):
            continue

        log_path = session_dir / "log.txt"
        log_text = ""
        if log_path.exists():
            raw = log_path.read_text(encoding="utf-8", errors="replace")
            if len(raw) > MAX_LOG_PER_SESSION:
                truncated = raw[:MAX_LOG_PER_SESSION]
                log_text = truncated + f"\n\n... (truncated, original size: {len(raw)} chars)\n"
            else:
                log_text = raw

        work_dir = files_dir / name
        file_list: list[str] = []
        if work_dir.exists():
            file_list = [p.name for p in sorted(work_dir.iterdir()) if p.is_file()]

        sessions.append({
            "name": name,
            "log_text": log_text,
            "files": file_list,
        })

    return sessions


def truncate_total_logs(sessions: list[dict]) -> list[dict]:
    """If total log size exceeds MAX_TOTAL_LOG_SIZE, drop oldest sessions."""
    total = sum(len(s["log_text"]) for s in sessions)
    if total <= MAX_TOTAL_LOG_SIZE:
        return sessions

    # Keep sessions from newest to oldest until we hit the limit
    kept = []
    current = 0
    for s in reversed(sessions):
        size = len(s["log_text"])
        if current + size > MAX_TOTAL_LOG_SIZE:
            break
        kept.append(s)
        current += size

    kept.reverse()
    print(f"[INFO] Truncated from {len(sessions)} to {len(kept)} sessions (total log size: {current} chars)")
    return kept


def read_memory_file(memory_dir: Path, filename: str) -> str:
    path = memory_dir / filename
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return f"(File not found: {filename})"


def build_prompt(sessions: list[dict], schema_text: str, index_text: str) -> str:
    parts = [
        "あなたは LLM-Wiki 記憶システムの管理者です。",
        "以下の SCHEMA に従って、セッションログから記憶を整理・更新してください。",
        "",
        "---",
        "",
        "# Memory Schema",
        "",
        schema_text,
        "",
        "---",
        "",
        "# Current Memory Index",
        "",
        index_text,
        "",
        "---",
        "",
        "# Target Session Logs",
        "",
    ]

    for s in sessions:
        parts.append(f"## Session: {s['name']}")
        if s["files"]:
            parts.append(f"**Files:** {', '.join(s['files'])}")
        parts.append("```")
        parts.append(s["log_text"])
        parts.append("```")
        parts.append("")

    parts.extend([
        "---",
        "",
        "# Instructions",
        "",
        "以下の操作を行ってください：",
        "",
        "1. **Ingest**: セッションログから新しい情報を抽出し、`entities/`、`topics/`、`sources/` のページを作成または更新してください。",
        "   - 既存ページがある場合は追記・修正し、重複を避けてください。",
        "   - 各ページの YAML frontmatter を必ず含めてください（type, created, updated, tags, sources）。",
        "   - ページ間は `[[WikiLinks]]` で相互参照してください。",
        "",
        "2. **Lint**: 記憶全体の整合性を確認してください。",
        "   - 矛盾がある場合は明示的に記録し、ページを更新してください。",
        "   - 孤立ページ（ inbound link がないページ）があれば、index.md から参照を追加してください。",
        "   - 重要な概念でまだ独立ページがないものがあれば、新規作成してください。",
        "",
        "3. **Update index.md**: 新規・更新ページを反映して index.md を更新してください。",
        "",
        "4. **Append log.md**: 今日の日付で以下の形式でエントリを追加してください。",
        "   ```markdown",
        "   ## [YYYY-MM-DD] ingest | Daily sync",
        "   - 処理したセッション数と主な更新内容の要約",
        "   ```",
        "",
        "5. **Language**: 日本語で記述してください（固有名詞・コードは除く）。",
        "",
        "以上。",
    ])

    return "\n".join(parts)


def get_kimi_path() -> str:
    """Return the absolute path to the Kimi CLI executable."""
    import shutil
    if path := shutil.which("kimi"):
        return path
    home = Path.home()
    candidates = [
        home / ".local" / "bin" / "kimi",
        home / ".cargo" / "bin" / "kimi",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    raise RuntimeError("kimi command not found")


async def run_kimi(prompt: str, work_dir: Path) -> str:
    cmd = [
        get_kimi_path(),
        "--yolo",
        "--quiet",
        "--session", MEMORY_SESSION_NAME,
        "--work-dir", str(work_dir),
        "--prompt", prompt,
    ]
    print(f"[INFO] Running Kimi CLI (session={MEMORY_SESSION_NAME}, work-dir={work_dir})")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
    except asyncio.TimeoutError:
        print("[ERROR] Kimi CLI timed out after 600 seconds", file=sys.stderr)
        proc.kill()
        return "[ERROR] Kimi CLI timed out after 600 seconds"

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        print(f"[ERROR] Kimi CLI failed (exit code {proc.returncode}):\n{err}", file=sys.stderr)
        return f"[ERROR] {err}"

    text = stdout.decode("utf-8", errors="replace").strip()
    # Strip trailing "To resume this session: ..." line
    lines = text.splitlines()
    if lines and lines[-1].startswith("To resume this session:"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def append_memory_log(memory_dir: Path, target_date: str, session_count: int, result: str) -> None:
    log_path = memory_dir / "log.md"
    now = datetime.now().strftime("%Y-%m-%d")
    entry = (
        f"\n## [{now}] ingest | Daily sync ({target_date})\n"
        f"- Sessions processed: {session_count}\n"
        f"- Result summary: {result[:200]}...\n"
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)


async def main() -> int:
    args = parse_args()
    workspace_dir = args.workspace or get_workspace_dir()
    memory_dir = workspace_dir / "memory"
    target_date = resolve_target_date(args.date)

    print(f"[INFO] Workspace: {workspace_dir}")
    print(f"[INFO] Target date: {target_date}")

    # Ensure memory directory exists
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "entities").mkdir(exist_ok=True)
    (memory_dir / "topics").mkdir(exist_ok=True)
    (memory_dir / "sources").mkdir(exist_ok=True)

    # Collect sessions
    sessions = collect_sessions(workspace_dir, target_date)
    sessions = truncate_total_logs(sessions)
    print(f"[INFO] Collected {len(sessions)} session(s)")

    if not sessions:
        print("[INFO] No sessions found for the target date. Nothing to do.")
        append_memory_log(memory_dir, target_date, 0, "No sessions found.")
        return 0

    # Read current memory state
    schema_text = read_memory_file(memory_dir, "SCHEMA.md")
    index_text = read_memory_file(memory_dir, "index.md")

    # Build prompt
    prompt = build_prompt(sessions, schema_text, index_text)
    print(f"[INFO] Prompt size: {len(prompt)} chars")

    # Run Kimi
    result = await run_kimi(prompt, memory_dir)

    # Log result
    append_memory_log(memory_dir, target_date, len(sessions), result)
    print(f"[INFO] Done. Memory log updated.")

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user.")
        exit_code = 130
    sys.exit(exit_code)
