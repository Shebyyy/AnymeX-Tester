import discord
from typing import Any, Callable, Dict, List, Optional

class ExtensionSelectDropdown(discord.ui.Select):
    def __init__(self, extensions: List[Dict[str, Any]], on_select_callback: Callable):
        options = []
        for ext in extensions[:25]:
            name = ext.get("name", "Unknown")[:50]
            pkg = ext.get("pkg", ext.get("id", ""))[:100]
            lang = ext.get("lang", "all")
            ver = ext.get("version", "1.0.0")
            desc = f"Lang: {lang.upper()} | v{ver} | {ext.get('backend', '').upper()}"[:100]

            options.append(discord.SelectOption(
                label=name,
                value=pkg,
                description=desc
            ))

        super().__init__(placeholder="Select an extension to test...", min_values=1, max_values=1, options=options)
        self.on_select_callback = on_select_callback

    async def callback(self, interaction: discord.Interaction):
        await self.on_select_callback(interaction, self.values[0])

class ExtensionListView(discord.ui.View):
    def __init__(self, extensions: List[Dict[str, Any]], on_select: Callable, page: int = 0, per_page: int = 25):
        super().__init__(timeout=180)
        self.extensions = extensions
        self.on_select = on_select
        self.page = page
        self.per_page = per_page
        self.max_pages = max(1, (len(extensions) + per_page - 1) // per_page)

        self._setup_components()

    def _setup_components(self):
        self.clear_items()
        start = self.page * self.per_page
        end = start + self.per_page
        page_items = self.extensions[start:end]

        if page_items:
            self.add_item(ExtensionSelectDropdown(page_items, self.on_select))

        if self.max_pages > 1:
            prev_btn = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary, disabled=(self.page == 0))
            prev_btn.callback = self._prev_callback
            self.add_item(prev_btn)

            indicator = discord.ui.Button(label=f"Page {self.page + 1}/{self.max_pages}", style=discord.ButtonStyle.primary, disabled=True)
            self.add_item(indicator)

            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, disabled=(self.page >= self.max_pages - 1))
            next_btn.callback = self._next_callback
            self.add_item(next_btn)

    async def _prev_callback(self, interaction: discord.Interaction):
        if self.page > 0:
            self.page -= 1
            self._setup_components()
            await interaction.response.edit_message(view=self)

    async def _next_callback(self, interaction: discord.Interaction):
        if self.page < self.max_pages - 1:
            self.page += 1
            self._setup_components()
            await interaction.response.edit_message(view=self)
