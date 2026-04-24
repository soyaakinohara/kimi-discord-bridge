import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from pathlib import Path

import config
from session_manager import SessionManager, Session
from search import brave_search, should_search, build_search_prompt

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
session_manager = SessionManager()


def split_message(text: str, limit: int = 2000) -> list[str]:
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_pos = text.rfind("\n", 0, limit)
        if split_pos == -1:
            split_pos = limit
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")
    return chunks


@tasks.loop(hours=1)
async def auto_cleanup():
    """24時間以上 inactive なセッションのファイルを自動削除し、スレッドをアーカイブする"""
    threshold = timedelta(hours=24)
    now = datetime.now()

    for thread_id, session in list(session_manager._sessions.items()):
        log_path = session.session_dir / "log.txt"
        if not log_path.exists():
            continue

        mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
        if now - mtime < threshold:
            continue

        # ファイル削除
        session_manager.cleanup_files(thread_id)

        # スレッドをアーカイブ
        thread = bot.get_channel(thread_id)
        if thread and isinstance(thread, discord.Thread):
            try:
                await thread.send("🧹 24時間以上 inactive だったので、添付ファイルを自動削除しました。")
                await thread.edit(archived=True, locked=False)
            except Exception as e:
                print(f"[auto_cleanup] Failed to archive thread {thread_id}: {e}")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    restored = len(session_manager._sessions)
    if restored:
        print(f"Restored {restored} persistent session(s)")
    try:
        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            synced = await bot.tree.sync(guild=guild)
            print(f"Synced {len(synced)} slash commands to guild {config.GUILD_ID}")
        else:
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} global slash commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

    auto_cleanup.start()


@bot.tree.command(name="new", description="新しいAIアシスタントセッションを開始します")
async def new_session(interaction: discord.Interaction):
    if isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message("スレッド内で `/new` は実行できません。通常のチャンネルで実行してください。", ephemeral=True)
        return

    # 先に defer して Discord のタイムアウト・リトライを防ぐ
    await interaction.response.defer(thinking=False)

    session = session_manager.prepare()
    thread = await interaction.channel.create_thread(
        name=session.name,
        type=discord.ChannelType.public_thread,
        reason="AI assistant session start"
    )
    session_manager.register(session, thread.id)

    await interaction.followup.send(f"セッション `{session.name}` を開始しました: {thread.mention}")

    # system_prompt.md があれば送信（オンボーディング後のみ存在）
    if config.SYSTEM_PROMPT_PATH.exists() and config.ONBOARDING_DONE_PATH.exists():
        await thread.send("🧠 システムプロンプトを読み込んでいます...")
        await session_manager.initialize_system_prompt(session)
        await thread.send(f"✅ セッション `{session.name}` の準備ができました。何か話しかけてください！")
    else:
        await thread.send(
            f"✅ セッション `{session.name}` の準備ができました。\n"
            "何か話しかけると、初期設定ウィザードが始まります！"
        )


@bot.tree.command(name="reset", description="現在のスレッドのセッションをリセットします")
async def reset_session(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message("`/reset` はスレッド内でのみ実行できます。", ephemeral=True)
        return

    thread_id = interaction.channel.id
    old_session = session_manager.remove(thread_id)

    if old_session:
        await interaction.response.send_message(f"🔄 セッション `{old_session.name}` をリセットします...")
    else:
        await interaction.response.send_message("🔄 セッションを新規作成します...")

    new_sess = session_manager.create(thread_id)

    if config.SYSTEM_PROMPT_PATH.exists() and config.ONBOARDING_DONE_PATH.exists():
        await interaction.channel.send("🧠 システムプロンプトを再読み込みしています...")
        await session_manager.initialize_system_prompt(new_sess)

    await interaction.channel.send(f"✅ 新しいセッション `{new_sess.name}` を開始しました。")


@bot.tree.command(name="stop", description="添付ファイルを削除してセッションを保持したまま、アーカイブします")
async def stop_session(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message("`/stop` はスレッド内でのみ実行できます。", ephemeral=True)
        return

    thread_id = interaction.channel.id
    session = session_manager.cleanup_files(thread_id)

    if session:
        await interaction.response.send_message(f"🛑 セッション `{session.name}` を一時停止します。添付ファイルを削除しました。")
    else:
        await interaction.response.send_message("🛑 セッションを一時停止します。")

    await interaction.channel.edit(archived=True, locked=False)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if not isinstance(message.channel, discord.Thread):
        return

    thread_id = message.channel.id
    session = session_manager.get(thread_id)
    if not session:
        print(f"[DEBUG] No session found for thread {thread_id}")
        return
    print(f"[DEBUG] Message in thread {thread_id}, session={session.name}, initialized={session.initialized}")

    # Bot自身へのメンションがない場合は無視しても良いが、
    # スレッド内では全メッセージをセッションに流す方が自然
    text = message.content
    if not text and not message.attachments:
        return

    # オンボーディングウィザードの判定
    is_onboarding = await session_manager.handle_onboarding(session, text or "", message.channel)
    if is_onboarding:
        return

    # 添付ファイルを保存
    attachment_paths: list[Path] = []
    if message.attachments:
        saved_names = []
        for att in message.attachments:
            save_path = session.work_dir / att.filename
            try:
                await att.save(save_path)
                attachment_paths.append(save_path)
                saved_names.append(att.filename)
                session.attachment_files.add(att.filename)
            except Exception as e:
                await message.channel.send(f"⚠️ ファイル `{att.filename}` の保存に失敗しました: {e}")
        if saved_names:
            await message.channel.send(f"📎 ファイルを保存しました: {', '.join(saved_names)}")

    async with message.channel.typing():
        try:
            prompt = text
            if should_search(text):
                await message.channel.send("🔍 検索を実行しています...")
                try:
                    results = await brave_search(text, count=5)
                    prompt = build_search_prompt(prompt, results)
                    summary = "\n".join([f"{i+1}. {r['title']}" for i, r in enumerate(results)])
                    await message.channel.send(f"🔍 検索結果:\n{summary}")
                except Exception as e:
                    await message.channel.send(f"⚠️ 検索に失敗しました: {e}")

            response, new_files = await session_manager.send_message(session, prompt, attachment_paths)
        except Exception as e:
            await message.channel.send(f"❌ エラーが発生しました: {e}")
            return

    if not response:
        response = "（応答なし）"

    chunks = split_message(response)
    for chunk in chunks:
        await message.channel.send(chunk)

    if new_files:
        await message.channel.send(f"💾 新しいファイルが作成されました: {', '.join(new_files)}")


@bot.tree.command(name="search", description="Brave Search で検索します")
@app_commands.describe(query="検索クエリ")
async def search_cmd(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    try:
        results = await brave_search(query, count=5)
        if not results:
            await interaction.followup.send("（検索結果はありませんでした）")
            return
        lines = ["🔍 検索結果:"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. [{r['title']}]({r['url']})")
            if r["description"]:
                lines.append(f"   {r['description']}")
        text = "\n".join(lines)
    except Exception as e:
        await interaction.followup.send(f"❌ 検索エラー: {e}")
        return

    chunks = split_message(text)
    for chunk in chunks:
        await interaction.followup.send(chunk)
