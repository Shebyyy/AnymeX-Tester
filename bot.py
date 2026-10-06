import asyncio
import logging
import os
import sys
from aiohttp import web
from dotenv import load_dotenv

import discord
from discord import app_commands
from discord.ext import commands

from runtime.downloader import RuntimeDownloader
from runtime.sidecar import SidecarBridge
from managers.repo_manager import RepoManager
from tester.extension_tester import ExtensionTester
from ui.embeds import create_test_report_embed, create_repo_embed, create_batch_test_embed
from ui.views import ExtensionListView

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s/%(levelname)s]: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AnymeXBot")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
PORT = int(os.getenv("PORT", "8080"))

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

repo_mgr = RepoManager()
tester = ExtensionTester()
downloader = RuntimeDownloader()
bridge = SidecarBridge()

# Render Health Check Web Server
async def handle_health(request):
    return web.Response(text="AnymeX Extension Testing Bot is Online 🚀", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Render health check server listening on port {PORT}")

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    
    # 1. Ensure runtime jar
    logger.info("Verifying AnymeX Desktop Runtime...")
    downloader.ensure_runtime()
    
    # 2. Start sidecar process
    logger.info("Initializing JVM Sidecar Bridge...")
    try:
        await bridge.start()
    except Exception as e:
        logger.error(f"Error starting sidecar on ready: {e}")

    # 3. Sync Slash Commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="/test_extension"
        )
    )

# --- Slash Commands ---

@bot.tree.command(name="status", description="Check bot runtime and sidecar status")
async def cmd_status(interaction: discord.Interaction):
    is_ready = bridge.is_running
    java_ok = downloader.is_java_available()
    jar_ok = downloader.is_jar_ready()
    repos_cnt = len(repo_mgr.get_repos())
    exts_cnt = len(repo_mgr.get_all_extensions())

    embed = discord.Embed(
        title="🤖 AnymeX Extension Bot Status",
        color=0x2ECC71 if is_ready else 0xE67E22
    )
    embed.add_field(name="Sidecar Process", value="🟢 Running" if is_ready else "🔴 Offline", inline=True)
    embed.add_field(name="Java (OpenJDK)", value="✅ Available" if java_ok else "❌ Missing", inline=True)
    embed.add_field(name="Bridge JAR", value="✅ Present" if jar_ok else "❌ Missing", inline=True)
    embed.add_field(name="Registered Repos", value=f"`{repos_cnt}`", inline=True)
    embed.add_field(name="Indexed Extensions", value=f"`{exts_cnt}`", inline=True)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="repo_add", description="Add an extension repository")
@app_commands.describe(
    url="Repository index or base URL",
    item_type="Media content type",
    backend="Extension backend system"
)
@app_commands.choices(
    item_type=[
        app_commands.Choice(name="Anime (Video)", value="anime"),
        app_commands.Choice(name="Manga (Images)", value="manga"),
        app_commands.Choice(name="Novel (Text)", value="novel"),
    ],
    backend=[
        app_commands.Choice(name="Aniyomi", value="aniyomi"),
        app_commands.Choice(name="CloudStream", value="cloudstream"),
        app_commands.Choice(name="Kotatsu", value="kotatsu"),
        app_commands.Choice(name="Mangayomi", value="mangayomi"),
        app_commands.Choice(name="LnReader", value="lnreader"),
        app_commands.Choice(name="Sora", value="sora"),
        app_commands.Choice(name="Legado", value="legado"),
    ]
)
async def cmd_repo_add(interaction: discord.Interaction, url: str, item_type: app_commands.Choice[str], backend: app_commands.Choice[str]):
    await interaction.response.defer()
    try:
        repo = await repo_mgr.add_repo(url=url, item_type=item_type.value, backend=backend.value)
        embed = create_repo_embed(repo)
        await interaction.followup.send(content="✅ Repository added and indexed successfully!", embed=embed)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to add repository: `{e}`")

@bot.tree.command(name="repo_list", description="List all registered repositories")
async def cmd_repo_list(interaction: discord.Interaction):
    repos = repo_mgr.get_repos()
    if not repos:
        await interaction.response.send_message("ℹ️ No repositories added yet. Use `/repo_add` to add one.")
        return

    embed = discord.Embed(
        title="📚 Registered Repositories",
        description=f"Total: `{len(repos)}` repositories",
        color=0x3498DB
    )
    for r in repos:
        embed.add_field(
            name=f"📦 {r.get('backend', '').upper()} ({r.get('itemType', '').title()})",
            value=f"• **Extensions:** `{r.get('extensionCount', 0)}`\n• **URL:** [Index Link]({r.get('url')})",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="repo_remove", description="Remove a registered repository")
@app_commands.describe(url="Repository URL to remove")
async def cmd_repo_remove(interaction: discord.Interaction, url: str):
    removed = repo_mgr.remove_repo(url.strip())
    if removed:
        await interaction.response.send_message(f"✅ Removed repository: `{url}`")
    else:
        await interaction.response.send_message(f"❌ Repository not found: `{url}`")

@bot.tree.command(name="extensions_list", description="Explore extensions with interactive selection")
@app_commands.describe(
    backend="Filter by backend",
    item_type="Filter by type"
)
@app_commands.choices(
    backend=[
        app_commands.Choice(name="Aniyomi", value="aniyomi"),
        app_commands.Choice(name="CloudStream", value="cloudstream"),
        app_commands.Choice(name="Kotatsu", value="kotatsu"),
        app_commands.Choice(name="Mangayomi", value="mangayomi"),
        app_commands.Choice(name="LnReader", value="lnreader"),
    ],
    item_type=[
        app_commands.Choice(name="Anime", value="anime"),
        app_commands.Choice(name="Manga", value="manga"),
        app_commands.Choice(name="Novel", value="novel"),
    ]
)
async def cmd_extensions_list(
    interaction: discord.Interaction,
    backend: Optional[app_commands.Choice[str]] = None,
    item_type: Optional[app_commands.Choice[str]] = None
):
    b_val = backend.value if backend else None
    t_val = item_type.value if item_type else None
    exts = repo_mgr.get_all_extensions(backend=b_val, item_type=t_val)

    if not exts:
        await interaction.response.send_message("ℹ️ No extensions found matching your filter.")
        return

    async def on_select(inter: discord.Interaction, selected_pkg: str):
        ext = repo_mgr.find_extension(selected_pkg)
        if not ext:
            await inter.response.send_message("❌ Extension not found.", ephemeral=True)
            return
        await inter.response.send_message(
            f"🎯 Selected **{ext.get('name')}** (`{ext.get('pkg')}`).\nUse `/test_extension name:{ext.get('name')} query:One Piece` to run tests!",
            ephemeral=True
        )

    view = ExtensionListView(exts, on_select=on_select)
    embed = discord.Embed(
        title="🧩 Extension Explorer",
        description=f"Showing `{len(exts)}` extensions. Select one from the menu below:",
        color=0x9B59B6
    )
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="test_extension", description="Run automated pipeline test on an extension")
@app_commands.describe(
    name="Name or package ID of the extension",
    query="Search query to test (e.g. One Piece, Solo Leveling)"
)
async def cmd_test_extension(interaction: discord.Interaction, name: str, query: str):
    await interaction.response.defer()

    ext = repo_mgr.find_extension(name)
    if not ext:
        await interaction.followup.send(f"❌ Extension `{name}` not found in registered repos. Check `/extensions_list`.")
        return

    progress_msg = await interaction.followup.send(f"⏳ **Testing `{ext.get('name')}`...** Preparing extension and running pipeline...")

    try:
        # Prepare / install extension if APK
        await repo_mgr.install_extension(ext)
        # Execute test
        report = await tester.run_test(ext, query)
        embed = create_test_report_embed(report)
        await progress_msg.edit(content=None, embed=embed)
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        await progress_msg.edit(content=f"❌ **Test Error:** `{e}`")

@bot.tree.command(name="test_repo", description="Test all extensions in a repository")
@app_commands.describe(
    url="Repository URL",
    query="Search query for tests"
)
async def cmd_test_repo(interaction: discord.Interaction, url: str, query: str):
    await interaction.response.defer()

    repos = repo_mgr.get_repos()
    matched_repo = next((r for r in repos if url.strip() in r.get("url", "") or url.strip() in r.get("indexUrl", "")), None)

    if not matched_repo:
        await interaction.followup.send(f"❌ Repository `{url}` not found. Check `/repo_list`.")
        return

    extensions = matched_repo.get("extensions", [])
    if not extensions:
        await interaction.followup.send("ℹ️ No extensions in this repository.")
        return

    progress = await interaction.followup.send(f"⏳ Starting batch test of `{len(extensions)}` extensions from `{matched_repo.get('url')}`...")

    results = []
    passed = 0
    failed = 0

    for i, ext in enumerate(extensions):
        try:
            await repo_mgr.install_extension(ext)
            rep = await tester.run_test(ext, query)
            results.append(rep)
            if rep.overall_passed:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1

        if (i + 1) % 5 == 0 or (i + 1) == len(extensions):
            try:
                await progress.edit(content=f"⏳ Tested `{i + 1}/{len(extensions)}` extensions... ({passed} passed, {failed} failed)")
            except Exception:
                pass

    summary_embed = create_batch_test_embed(matched_repo.get("url"), passed, failed, results)
    await progress.edit(content=None, embed=summary_embed)

async def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_discord_bot_token_here":
        logger.warning("DISCORD_TOKEN is not set in .env! Please set your bot token.")

    # Start health server for Render in parallel
    await start_web_server()

    if DISCORD_TOKEN and DISCORD_TOKEN != "your_discord_bot_token_here":
        async with bot:
            await bot.start(DISCORD_TOKEN)
    else:
        logger.info("Bot is in test/dry-run mode without token. Keeping web server alive.")
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        bridge.stop()
