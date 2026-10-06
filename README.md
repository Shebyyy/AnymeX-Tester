# 🤖 AnymeX Extension Testing Bot

A powerful Discord bot designed to discover, manage, and automatically test all content extensions supported by the **AnymeX Extension Runtime Bridge** across Anime, Manga, and Light Novels.

---

## 🚀 Features

- 📦 **Multi-Backend Support**: Aniyomi, CloudStream, Kotatsu, Mangayomi, LnReader, Sora, and Legado.
- ⚡ **Automated End-to-End Pipeline**:
  1. **Phase 1: Search** — Queries the source, tests latency, and captures initial results.
  2. **Phase 2: Details & Episodes/Chapters** — Retrieves detailed media metadata and parses episode/chapter lists.
  3. **Phase 3: Stream & Media Health Check**:
     - **Anime**: Extracts video streams, qualities (1080p, 720p), and performs live `HTTP HEAD/GET Range` checks to confirm stream URLs return `200/206 OK`.
     - **Manga**: Extracts chapter page lists and verifies image links.
     - **Novel**: Extracts chapter text and validates character count and previews.
- ☕ **Auto-Provisioned Java Sidecar**: Automatically checks and downloads `anymex_desktop_runtime.jar` directly from RyanYuuki's latest GitHub release on startup.
- 🌐 **Ready for Render Deployment**: Includes health check server and Dockerfile with Python 3.11 + OpenJDK 17.

---

## 📜 Slash Commands

| Command | Description |
|---|---|
| `/status` | Check Sidecar process, Java availability, and indexed counts |
| `/repo_add <url> <item_type> <backend>` | Add & index an extension repository |
| `/repo_list` | List all registered repositories |
| `/repo_remove <url>` | Remove a registered repository |
| `/extensions_list [backend] [type]` | Browse extensions with an interactive dropdown & pagination |
| `/test_extension <name> <query>` | Run full automated pipeline test on an extension |
| `/test_repo <url> <query>` | Batch test all extensions in a repository with a summary card |

---

## 🛠️ Local Setup

### 1. Requirements
- Python 3.10+
- Java (OpenJDK 17 recommended for sidecar extensions like Aniyomi/CloudStream)

### 2. Installation
```bash
git clone https://github.com/Shebyyy/AnymeX-Extension-Bot.git
cd AnymeX-Extension-Bot

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment Variables
Copy `.env.example` to `.env`:
```env
DISCORD_TOKEN=your_bot_token_here
PORT=8080
```

### 4. Run the Bot
```bash
python bot.py
```
*On first startup, the bot will automatically download `anymex_desktop_runtime.jar` from Ryan's repository.*

---

## ☁️ Deploying to Render

1. Create a new **Web Service** on [Render](https://render.com/).
2. Connect your `AnymeX-Extension-Bot` repository.
3. Select **Docker** environment (Render will automatically detect the provided `Dockerfile`).
4. Set the Environment Variables:
   - `DISCORD_TOKEN` = `your_discord_bot_token`
   - `PORT` = `8080`
5. Click **Create Web Service**. The container will start with Python 3.11, OpenJDK 17, and the auto-downloaded sidecar runtime!

---

*Maintained with ❤️ for the AnymeX community.*
