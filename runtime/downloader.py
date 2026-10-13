import asyncio
import json
import logging
import os
import shutil
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger("RuntimeDownloader")

API_URL = "https://api.github.com/repos/RyanYuuki/AnymeXExtensionRuntimeBridge/releases/latest"
JAR_URL = "https://github.com/RyanYuuki/AnymeXExtensionRuntimeBridge/releases/latest/download/anymex_desktop_runtime.jar"


class RuntimeDownloader:
    def __init__(self, tools_dir: str = "data/tools"):
        self.tools_dir = os.path.abspath(tools_dir)
        self.jar_path = os.path.join(self.tools_dir, "anymex_desktop_runtime.jar")
        self.meta_path = os.path.join(self.tools_dir, "runtime_meta.json")
        os.makedirs(self.tools_dir, exist_ok=True)

    def is_java_available(self) -> bool:
        return shutil.which("java") is not None

    def is_jar_ready(self) -> bool:
        if not os.path.exists(self.jar_path):
            return False
        return os.path.getsize(self.jar_path) > 1024 * 1024  # At least 1MB

    def _load_meta(self) -> Dict[str, Any]:
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_meta(self, meta: Dict[str, Any]):
        try:
            with open(self.meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save runtime meta: {e}")

    def fetch_latest_release_info(self) -> Optional[Dict[str, Any]]:
        """Queries GitHub API for latest runtime JAR release metadata."""
        try:
            req = urllib.request.Request(
                API_URL,
                headers={
                    "User-Agent": "AnymeX-Extension-Bot/1.0",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                if response.status != 200:
                    return None
                data = json.loads(response.read().decode("utf-8"))
                tag = data.get("tag_name", "")
                assets = data.get("assets", [])

                for a in assets:
                    if a.get("name") == "anymex_desktop_runtime.jar":
                        return {
                            "tag": tag,
                            "size": a.get("size", 0),
                            "updated_at": a.get("updated_at", ""),
                            "download_url": a.get("browser_download_url", JAR_URL),
                        }
        except Exception as e:
            logger.warning(f"Failed to check GitHub for runtime updates: {e}")
        return None

    def download_runtime(self, download_url: str = JAR_URL) -> bool:
        """Downloads the runtime JAR safely using a temp file."""
        logger.info(f"Downloading desktop runtime JAR from {download_url}...")
        tmp_path = self.jar_path + ".tmp"
        try:
            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": "AnymeX-Extension-Bot/1.0"},
            )
            with urllib.request.urlopen(req, timeout=60) as response, open(tmp_path, "wb") as out_file:
                shutil.copyfileobj(response, out_file)

            if os.path.exists(self.jar_path):
                os.remove(self.jar_path)
            os.rename(tmp_path, self.jar_path)
            logger.info(f"Successfully installed AnymeX Desktop Runtime JAR ({os.path.getsize(self.jar_path)} bytes).")
            return True
        except Exception as e:
            logger.error(f"Failed to download Desktop Runtime JAR: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False

    async def auto_update_runtime(self, bridge=None) -> bool:
        """Checks for new runtime updates before running tests. Updates and restarts sidecar if needed."""
        if not self.is_java_available():
            logger.warning("Java is not found in PATH!")

        latest = await asyncio.to_thread(self.fetch_latest_release_info)
        local_meta = self._load_meta()

        needs_download = False
        if not self.is_jar_ready():
            needs_download = True
        elif latest:
            # Compare remote release with stored local meta
            if (
                latest.get("tag") != local_meta.get("tag")
                or latest.get("updated_at") != local_meta.get("updated_at")
                or latest.get("size") != os.path.getsize(self.jar_path)
            ):
                logger.info(f"New runtime JAR detected! (Remote: {latest.get('tag')}, Local: {local_meta.get('tag')}). Updating...")
                needs_download = True

        if needs_download:
            download_url = latest.get("download_url", JAR_URL) if latest else JAR_URL
            # If bridge is currently running, stop it first before replacing the JAR file
            if bridge and bridge.is_running:
                logger.info("Stopping JVM sidecar to replace runtime JAR...")
                bridge.stop()

            success = await asyncio.to_thread(self.download_runtime, download_url)
            if success:
                if latest:
                    self._save_meta(latest)
                if bridge:
                    logger.info("Restarting JVM sidecar with new runtime JAR...")
                    await bridge.start()
                return True
            else:
                return self.is_jar_ready()

        return True

    def ensure_runtime(self) -> bool:
        """Initial check on bot boot."""
        if self.is_jar_ready():
            return True
        return self.download_runtime()
