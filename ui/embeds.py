import discord
from typing import Any, Dict, List
from tester.extension_tester import TestReport

BACKEND_ICONS = {
    "aniyomi": "https://aniyomi.org/img/logo-128px.png",
    "cloudstream": "https://static.everythingmoe.com/icons/cloudstream.png",
    "kotatsu": "https://raw.githubusercontent.com/KotatsuApp/Kotatsu/devel/metadata/en-US/icon.png",
    "mangayomi": "https://raw.githubusercontent.com/kodjodevf/mangayomi/main/assets/app_icons/icon-red.png",
}

def create_test_report_embed(report: TestReport) -> discord.Embed:
    status_emoji = "🟢" if report.overall_passed else "🔴"
    status_text = "PASSED" if report.overall_passed else "FAILED"
    color = 0x2ECC71 if report.overall_passed else 0xE74C3C

    embed = discord.Embed(
        title=f"{status_emoji} Extension Test: {report.extension_name}",
        description=f"**Backend:** `{report.backend.upper()}` | **Type:** `{report.item_type.title()}`\n**Search Query:** `{report.query}`",
        color=color
    )

    # Step 1: Search
    if report.search_step:
        step = report.search_step
        icon = "✅" if step.passed else "❌"
        value = f"{step.info}" if step.passed else f"⚠️ **Error:** `{step.error}`"
        embed.add_field(
            name=f"{icon} Step 1: Search ({step.duration_ms}ms)",
            value=value,
            inline=False
        )

    # Step 2: Details
    if report.detail_step:
        step = report.detail_step
        icon = "✅" if step.passed else "❌"
        value = f"{step.info}" if step.passed else f"⚠️ **Error:** `{step.error}`"
        embed.add_field(
            name=f"{icon} Step 2: Details & List ({step.duration_ms}ms)",
            value=value,
            inline=False
        )

    # Step 3: Content Extraction
    if report.content_step:
        step = report.content_step
        icon = "✅" if step.passed else "❌"
        lines = []
        if step.passed:
            lines.append(f"ℹ️ {step.info}")
            if report.video_streams:
                lines.append("\n**Verified Video Streams:**")
                for s in report.video_streams:
                    s_icon = "🟢" if s.alive else "🔴"
                    s_status = f"HTTP {s.status_code} OK" if s.alive else (s.error or "Offline")
                    lines.append(f"{s_icon} **{s.quality}** — `{s_status}`")
            elif report.novel_snippet:
                lines.append(f"\n📖 **Preview:**\n> {report.novel_snippet}...")
        else:
            lines.append(f"⚠️ **Error:** `{step.error}`")

        embed.add_field(
            name=f"{icon} Step 3: Content Extraction ({step.duration_ms}ms)",
            value="\n".join(lines),
            inline=False
        )

    embed.set_footer(text=f"Total Elapsed Time: {report.total_duration_ms}ms | Status: {status_text}")
    return embed

def create_repo_embed(repo: Dict[str, Any]) -> discord.Embed:
    embed = discord.Embed(
        title=f"📦 Repository: {repo.get('backend', '').upper()} ({repo.get('itemType', '').title()})",
        description=f"**URL:** {repo.get('url')}\n**Available Extensions:** `{repo.get('extensionCount', 0)}`",
        color=0x3498DB
    )
    extensions = repo.get("extensions", [])[:15]
    if extensions:
        ext_list = [f"• **{e.get('name')}** (`{e.get('lang', 'all')}`) v{e.get('version')}" for e in extensions]
        if repo.get("extensionCount", 0) > 15:
            ext_list.append(f"*... and {repo.get('extensionCount', 0) - 15} more*")
        embed.add_field(name="Extensions Sample", value="\n".join(ext_list), inline=False)
    return embed

def create_batch_test_embed(repo_url: str, passed: int, failed: int, results: List[TestReport]) -> discord.Embed:
    total = passed + failed
    rate = int((passed / total * 100)) if total > 0 else 0
    color = 0x2ECC71 if rate >= 80 else 0xF39C12 if rate >= 50 else 0xE74C3C

    embed = discord.Embed(
        title="📊 Repository Batch Test Summary",
        description=f"**Repo:** {repo_url}\n**Passed:** `{passed}/{total}` ({rate}% pass rate)",
        color=color
    )

    summary_lines = []
    for r in results:
        icon = "✅" if r.overall_passed else "❌"
        err = f" ({r.content_step.error or r.search_step.error})" if not r.overall_passed and (r.content_step or r.search_step) else ""
        summary_lines.append(f"{icon} **{r.extension_name}** — `{r.total_duration_ms}ms`{err}")

    embed.add_field(name="Results Breakdown", value="\n".join(summary_lines[:25]), inline=False)
    return embed
