import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", "./workspace")).resolve()
GUILD_ID = os.getenv("GUILD_ID", "")
GUILD_ID = int(GUILD_ID) if GUILD_ID else None
SYSTEM_PROMPT_PATH = WORKSPACE_DIR / "system_prompt.md"
MEMORY_DIR = WORKSPACE_DIR / "memory"
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

# .env で明示指定がなければ PATH から自動検出、それでもなければフォールバック
KIMI_PATH = os.getenv("KIMI_PATH") or shutil.which("kimi") or "kimi"

# Onboarding paths
ONBOARDING_STATE_PATH = WORKSPACE_DIR / "onboarding_state.json"
ONBOARDING_DONE_PATH = WORKSPACE_DIR / ".onboarding_done"

ONBOARDING_QUESTIONS = [
    "ようこそ！まず、私（AIアシスタント）の名前を決めてください。何と呼んでほしいですか？",
    "ありがとうございます！次に、あなたの名前を教えてください。どのようにお呼びすればいいですか？",
    "どんな口調や性格が好みですか？（例: 丁寧語、フレンドリー、ツンデレ、毒舌、冷静沈着など）",
    "特に使ってほしい絵文字や、避けてほしい表現はありますか？（なければ「なし」と答えてください）",
]

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN is not set in environment variables.")

WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
(WORKSPACE_DIR / "files").mkdir(exist_ok=True)
(WORKSPACE_DIR / "sessions").mkdir(exist_ok=True)
MEMORY_DIR.mkdir(exist_ok=True)
(MEMORY_DIR / "entities").mkdir(exist_ok=True)
(MEMORY_DIR / "topics").mkdir(exist_ok=True)
(MEMORY_DIR / "sources").mkdir(exist_ok=True)
(MEMORY_DIR / "hardware").mkdir(exist_ok=True)
(MEMORY_DIR / "synthesis").mkdir(exist_ok=True)
