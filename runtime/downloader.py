import os
import shutil
import urllib.request
import logging

logger = logging.getLogger("RuntimeDownloader")

JAR_URL = "https://github.com/RyanYuuki/AnymeXExtensionRuntimeBridge/releases/latest/download/anymex_desktop_runtime.jar"

class RuntimeDownloader:
    def __init__(self, tools_dir: str = "data/tools"):
        self.tools_dir = os.path.abspath(tools_dir)
        self.jar_path = os.path.join(self.tools_dir, "anymex_desktop_runtime.jar")
        os.makedirs(self.tools_dir, exist_ok=True)

    def is_java_available(self) -> bool:
        return shutil.which("java") is not None

    def is_jar_ready(self) -> bool:
        if not os.path.exists(self.jar_path):
            return False
        return os.path.getsize(self.jar_path) > 1024 * 1024  # At least 1MB

    def ensure_runtime(self) -> bool:
        """Ensures the JAR exists. Downloads if missing."""
        if not self.is_java_available():
            logger.warning("Java is not found in PATH! Desktop sidecar extensions (Aniyomi, CloudStream, Kotatsu) require OpenJDK 17.")

        if self.is_jar_ready():
            logger.info(f"AnymeX Desktop Runtime JAR is already present at {self.jar_path}")
            return True

        logger.info(f"Downloading anymex_desktop_runtime.jar from {JAR_URL}...")
        tmp_path = self.jar_path + ".tmp"
        try:
            req = urllib.request.Request(
                JAR_URL,
                headers={"User-Agent": "AnymeX-Extension-Bot/1.0"}
            )
            with urllib.request.urlopen(req) as response, open(tmp_path, "wb") as out_file:
                shutil.copyfileobj(response, out_file)

            if os.path.exists(self.jar_path):
                os.remove(self.jar_path)
            os.rename(tmp_path, self.jar_path)
            logger.info(f"Successfully downloaded AnymeX Desktop Runtime JAR ({os.path.getsize(self.jar_path)} bytes).")
            return True
        except Exception as e:
            logger.error(f"Failed to download Desktop Runtime JAR: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False
