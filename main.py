import asyncio
import atexit
import os
import sys
from pathlib import Path

import config
from bot import bot

PID_FILE = Path(__file__).parent / ".bot.pid"


def _is_process_running(pid: int) -> bool:
    """指定PIDのプロセスが実際に存在するか確認"""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _acquire_lock() -> None:
    """PIDファイルで二重起動を防止する"""
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            if old_pid != os.getpid() and _is_process_running(old_pid):
                print(f"Error: Bot is already running (PID {old_pid}).", file=sys.stderr)
                print(f"If the old process is dead, delete {PID_FILE} and try again.", file=sys.stderr)
                sys.exit(1)
        except (ValueError, OSError):
            pass
        # 古いPIDファイルが残っていたら削除
        PID_FILE.unlink(missing_ok=True)

    PID_FILE.write_text(str(os.getpid()))


def _release_lock() -> None:
    """PIDファイルを削除"""
    PID_FILE.unlink(missing_ok=True)


def main():
    _acquire_lock()
    atexit.register(_release_lock)

    print("Starting Kimi Discord Bridge...")
    print(f"Workspace: {config.WORKSPACE_DIR}")
    print(f"System Prompt: {config.SYSTEM_PROMPT_PATH} (exists={config.SYSTEM_PROMPT_PATH.exists()})")
    bot.run(config.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
