# Kimi Discord Bridge

[Kimi Code CLI](https://github.com/MoonshotAI/Kimi-CLI)（または互換のCLIアシスタント）用の **Discordラッパーボット** です。Discordのスレッドを永続的でファイル対応のAIセッションに変換し、オプションでLLM-Wiki記憶システムやWeb検索を利用できます。

> 🚀 **初回ユーザーにはオンボーディングウィザード** — ボットに話しかけるだけで、アシスタントの名前・あなたの名前・性格・好みを尋ね、自動的にパーソナライズされたシステムプロンプトを生成します。

---

## 注意  
このコードはkimi-k2.6が自律的に書き上げたコードで、指示した私は一般人なので恥ずかしながらコードを読むことができません。  
このコードを用いて何が起きようが自己責任になります。
これは私があくまで、既存のエージェントハーネスの必要な機能のみを軽量で安定した環境で使用するために個人的に作成したものです。  
機能追加はするかもしれませんが期待しないこと。    
kimi-cliはすべてのコマンドを自動許可するモードで動かしているため、誤ったディレクトリを削除したりマシンを爆破する可能性があります。  
バックアップ可能な環境（proxmoxVEなど）で動かすことを強く推奨します  
  
## 機能

| 機能 | 説明 |
|---------|-------------|
| **スレッド = セッション** | Discordの各スレッドが独立したCLIセッションになり、専用の作業ディレクトリを持ちます。 |
| **永続セッション** | ボット再起動後もセッションが継続。メタデータとログは `workspace/sessions/` に保存されます。 |
| **ファイル添付** | スレッドにファイルをドラッグ＆ドロップすると、セッションの作業ディレクトリに自動保存されます。 |
| **Web検索** | ユーザーが調べものを頼んだ場合に自動で検索を実行（Brave Search API）し、手動 `/search` コマンドも利用可能です。 |
| **LLM-Wiki記憶** | Markdownベースの個人知識ベース (`workspace/memory/`) を、アシスタントがセッションを跨いで読み書きします。 |
| **オンボーディングウィザード** | チャットでの初回設定。`system_prompt.md` を手動で編集する必要がありません。 |
| **自動クリーンアップ** | 24時間以上 inactive なセッションは自動的にアーカイブされ、添付ファイルが削除されます。 |
| **毎日の記憶同期** | オプションのcronスクリプト (`scripts/daily_memory_sync.py`) で、昨日のログをWikiに反映します。 |

---

## 必要条件

- Python **3.11+**
- [Kimi CLI](https://github.com/MoonshotAI/Kimi-CLI) がインストールされ、`PATH` に通っていること（または `KIMI_PATH` を設定）
- **Discord Bot Token** ([ここで作成](https://discord.com/developers/applications))
- *(オプション)* **Brave Search API Key** — Web検索を有効化する場合 ([ここで取得](https://api.search.brave.com/app/keys))

---

## インストール

```bash
git clone https://github.com/yourname/kimi-discord-bridge.git
cd kimi-discord-bridge
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 1. `.env` を作成

```bash
cp .env.example .env
```

`.env` を編集:

```env
DISCORD_TOKEN=your_discord_bot_token_here
WORKSPACE_DIR=./workspace
# GUILD_ID=123456789012345678   # オプション: 即時スラッシュコマンド同期用
# BRAVE_API_KEY=your_key_here   # オプション: Web検索を有効化
# KIMI_PATH=/usr/local/bin/kimi # オプション: PATH にない場合
```

### 2. Discord Intents を有効化

[Discord Developer Portal](https://discord.com/developers/applications) で:

1. **Bot** → **Message Content Intent** をオンにする。
2. **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot permissions: `Send Messages`, `Create Public Threads`, `Read Message History`, `Attach Files`, `Embed Links`, `Use Slash Commands`
3. 生成されたURLを開き、ボットをサーバーに招待する。

### 3. 実行

```bash
python main.py
```

ボットが起動し、スラッシュコマンドを同期してログイン確認を表示します。

---

## 使い方

| コマンド | 説明 |
|---------|-------------|
| `/new` | 公開スレッドで新しいAIセッションを開始します。 |
| `/reset` | 現在のスレッドのセッションをリセットします（スレッドは保持）。 |
| `/stop` | 添付ファイルを削除し、セッションメタデータを保持したままスレッドをアーカイブします。 |
| `/search <query>` | Brave Search を実行して結果を返します。 |

### 初回設定（オンボーディング）

1. 任意のチャンネルで `/new` と入力します。
2. ボットがスレッドを作成します。
3. スレッドで **何か話しかける** と、オンボーディングウィザードが始まります:
   - アシスタントの名前
   - あなたの名前 / 呼び方
   - 性格 / 口調
   - 絵文字 / 表現の好み
4. ボットが `workspace/system_prompt.md` を自動生成し、通常のチャットを開始します。

> ウィザードをスキップする場合は、`workspace/system_prompt.md` を手動で編集し、空のファイル `workspace/.onboarding_done` を作成してください。

---

## ディレクトリ構成

```
kimi-discord-bridge/
├── bot.py                  # Discordボットロジック
├── session_manager.py      # セッション管理 & Kimi CLIラッパー
├── search.py               # Brave Search API連携
├── config.py               # 環境変数 & パス設定
├── main.py                 # エントリポイント（PIDロック付き）
├── scripts/
│   └── daily_memory_sync.py   # オプション: Wikiメンテナンス用cronジョブ
├── workspace/
│   ├── system_prompt.md    # オンボーディングで生成（または手書き）
│   ├── .onboarding_done    # フラグファイル — 存在するとウィザードをスキップ
│   ├── memory/
│   │   ├── SCHEMA.md       # Wikiスキーマルール
│   │   ├── index.md        # コンテンツカタログ
│   │   ├── entities/       # 人物、プロジェクト、ツールなど
│   │   ├── topics/         # 概念、技術
│   │   ├── sources/        # ドキュメント要約
│   │   ├── hardware/       # ハードウェア情報
│   │   └── synthesis/      # 総合分析
│   ├── files/              # セッション作業ディレクトリ
│   └── sessions/           # セッションログ & メタデータ
├── .env                    #  secrets（gitignored）
├── .env.example            # テンプレート
└── requirements.txt
```

---

## 記憶システム（LLM-Wiki）

ボットは `workspace/memory/SCHEMA.md` と `workspace/memory/index.md` を、新規セッションのシステムプロンプトの一部として注入します。AIアシスタントは以下を行うことが期待されます:

- **Ingest**: 会話後に新しい事実をWikiに書き込む。
- **Query**: 質問に答える前にWikiを参照する。
- **Lint**: 定期的にWikiの整合性を確認する（孤立ページ、矛盾、古い情報のチェック）。

毎日の同期を手動で実行する場合:

```bash
python scripts/daily_memory_sync.py
# または特定の日付を指定
python scripts/daily_memory_sync.py --date 20260423
```

cron に登録することも可能（毎日6時に実行）:

```cron
0 6 * * * cd /path/to/kimi-discord-bridge && venv/bin/python scripts/daily_memory_sync.py >> workspace/logs/memory_sync.log 2>&1
```

---

## カスタマイズ

- **後からアシスタントの人格を変更**: `workspace/system_prompt.md` を編集し、スレッドで `/reset` を実行してください。
- **検索を無効化**: `.env` の `BRAVE_API_KEY` を空にしてください。
- **記憶システムを無効化**: `workspace/memory/SCHEMA.md` を削除または空にしてください。

---

## トラブルシューティング

| 問題 | 解決策 |
|---------|----------|
| スラッシュコマンドが表示されない | グローバル同期には最大1時間かかる場合があります。即時に同期するには `GUILD_ID` を設定してください。 |
| Bot が "Kimi CLI Error" と表示 | `kimi` がインストールされ `PATH` に通っているか、または `KIMI_PATH` が正しく設定されているか確認してください。 |
| 検索に失敗する | `BRAVE_API_KEY` が有効で、残りのクォータがあるか確認してください。 |
| セッションが永続化されない | `workspace/sessions/` が書き込み可能で、揮発性のファイルシステム上にないか確認してください。 |
| オンボーディングが繰り返される | `workspace/.onboarding_done` を手動で作成してスキップしてください。 |

---

## ライセンス

MIT — 好きに使ってください。ただしAIが自我に目覚めてあなたのコードをdisり始めても責任は取れません。  
↑kimi k2.6の素敵なジョーク。kimi-k2.6を開発してくれたmoonshotAI感謝を

## 連絡先
このコードはXの@soyaakinohara4がkimi-k2.6を用いて作成しました。何かあればここまでお願いします。
