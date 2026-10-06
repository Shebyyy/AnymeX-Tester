import aiohttp
import asyncio
import gzip
import json
import logging
import os
from typing import Any, Dict, List, Optional
from runtime.sidecar import SidecarBridge

logger = logging.getLogger("RepoManager")

class RepoManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = os.path.abspath(data_dir)
        self.repos_file = os.path.join(self.data_dir, "repos.json")
        self.ext_dir = os.path.join(self.data_dir, "extensions")
        os.makedirs(self.ext_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        self.repos: List[Dict[str, Any]] = self._load_repos()

    def _load_repos(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.repos_file):
            try:
                with open(self.repos_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading repos.json: {e}")
        return []

    def _save_repos(self):
        try:
            with open(self.repos_file, "w", encoding="utf-8") as f:
                json.dump(self.repos, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving repos.json: {e}")

    async def fetch_repo_index(self, url: str) -> List[Dict[str, Any]]:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AnymeX-Bot/1.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status} fetching repo index")
                body = await resp.read()

                # Handle gzip if present
                if len(body) >= 2 and body[0] == 0x1F and body[1] == 0x8B:
                    try:
                        body = gzip.decompress(body)
                    except Exception as e:
                        logger.warning(f"Failed to gzip-decompress repo body: {e}")

                try:
                    text = body.decode("utf-8", errors="replace")
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return parsed
                    elif isinstance(parsed, dict) and "extensions" in parsed:
                        return parsed["extensions"]
                    elif isinstance(parsed, dict) and "sources" in parsed:
                        return parsed["sources"]
                    return []
                except Exception as e:
                    raise RuntimeError(f"Failed to parse repo JSON: {e}")

    async def add_repo(self, url: str, item_type: str, backend: str) -> Dict[str, Any]:
        url = url.strip()
        clean_url = url
        if not clean_url.endswith(".json") and not clean_url.endswith(".gz"):
            if not clean_url.endswith("/"):
                clean_url += "/"
            clean_url += "index.min.json"

        raw_extensions = await self.fetch_repo_index(clean_url)
        parsed_sources = []

        base_icon_url = clean_url.rsplit("/", 1)[0]

        for item in raw_extensions:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "Unknown")
            # Strip "Aniyomi: " or "Tachiyomi: " prefix for cleaner display
            clean_name = name
            if clean_name.startswith("Aniyomi: "):
                clean_name = clean_name[9:]
            elif clean_name.startswith("Tachiyomi: "):
                clean_name = clean_name[11:]

            pkg = item.get("pkg", item.get("pkgName", item.get("id", "")))
            apk = item.get("apk", item.get("apkUrl", ""))
            version = str(item.get("version", "1.0.0"))
            lang = item.get("lang", "all")
            is_nsfw = bool(item.get("nsfw", item.get("isNsfw", False)))

            # Extract numeric source ID from sources list (critical for Aniyomi)
            sources = item.get("sources", [])
            first_source_id = ""
            if isinstance(sources, list) and len(sources) > 0 and isinstance(sources[0], dict):
                first_source_id = str(sources[0].get("id", ""))
            
            source_id = first_source_id or str(item.get("id", pkg))

            icon = item.get("iconUrl", "")
            if not icon:
                icon = f"{base_icon_url}/icon/{pkg}.png"

            apk_url = apk if apk.startswith("http") else f"{base_icon_url}/apk/{apk}" if apk else ""

            # Detect item type accurately from pkg or type
            detected_type = item_type.lower()
            if ".animeextension." in pkg or ".anime." in pkg:
                detected_type = "anime"
            elif ".mangaextension." in pkg or ".manga." in pkg:
                detected_type = "manga"

            source_entry = {
                "id": source_id,
                "name": clean_name,
                "rawName": name,
                "pkg": pkg,
                "version": version,
                "lang": lang,
                "isNsfw": is_nsfw,
                "icon": icon,
                "apkUrl": apk_url,
                "backend": backend.lower(),
                "itemType": detected_type,
                "repoUrl": url
            }
            parsed_sources.append(source_entry)

        # Remove existing repo if same url
        self.repos = [r for r in self.repos if r.get("url") != url]

        repo_entry = {
            "url": url,
            "indexUrl": clean_url,
            "backend": backend.lower(),
            "itemType": item_type.lower(),
            "extensionCount": len(parsed_sources),
            "extensions": parsed_sources
        }

        self.repos.append(repo_entry)
        self._save_repos()
        return repo_entry

    def remove_repo(self, url: str) -> bool:
        initial_len = len(self.repos)
        self.repos = [r for r in self.repos if r.get("url") != url]
        if len(self.repos) < initial_len:
            self._save_repos()
            return True
        return False

    def get_repos(self, backend: Optional[str] = None) -> List[Dict[str, Any]]:
        if backend:
            return [r for r in self.repos if r.get("backend") == backend.lower()]
        return self.repos

    def get_all_extensions(self, backend: Optional[str] = None, item_type: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        for r in self.repos:
            if backend and r.get("backend") != backend.lower():
                continue
            if item_type and r.get("itemType") != item_type.lower():
                continue
            results.extend(r.get("extensions", []))
        return results

    def find_extension(self, query: str) -> Optional[Dict[str, Any]]:
        query_lower = query.lower().strip()
        all_exts = self.get_all_extensions()
        # Exact match on name, pkg, or id
        for ext in all_exts:
            if (ext.get("name", "").lower() == query_lower or 
                ext.get("pkg", "").lower() == query_lower or 
                ext.get("id", "").lower() == query_lower or
                ext.get("rawName", "").lower() == query_lower):
                return ext
        # Partial match
        for ext in all_exts:
            if (query_lower in ext.get("name", "").lower() or 
                query_lower in ext.get("pkg", "").lower() or
                query_lower in ext.get("rawName", "").lower()):
                return ext
        return None

    async def install_extension(self, ext: Dict[str, Any]) -> bool:
        """Downloads APK/JAR, converts to JAR if needed, and registers with sidecar."""
        backend = ext.get("backend", "")
        pkg = ext.get("pkg", "ext")
        apk_url = ext.get("apkUrl")

        bridge = SidecarBridge()
        target_jar = os.path.join(self.ext_dir, f"{pkg}.jar")

        if os.path.exists(target_jar):
            # Already installed/converted -> reload into sidecar
            loaded = await bridge.invoke_method("loadExtensions", {"folderPath": self.ext_dir})
            self._sync_loaded_id(ext, loaded)
            return True

        if not apk_url:
            return False

        temp_zip = os.path.join(self.ext_dir, f"{pkg}.zip")
        headers = {"User-Agent": "Mozilla/5.0"}

        logger.info(f"Downloading APK for {ext.get('name')} from {apk_url}...")
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(apk_url) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Failed to download extension APK: HTTP {resp.status}")
                with open(temp_zip, "wb") as f:
                    f.write(await resp.read())

        try:
            logger.info(f"Converting APK {pkg} to JAR via sidecar dex2jar...")
            await bridge.invoke_method("convertApk", {
                "apkPath": temp_zip,
                "outJarPath": target_jar
            })

            # Reload extensions in sidecar JVM
            loaded = await bridge.invoke_method("loadExtensions", {"folderPath": self.ext_dir})
            self._sync_loaded_id(ext, loaded)
            return True
        finally:
            if os.path.exists(temp_zip):
                try:
                    os.remove(temp_zip)
                except Exception:
                    pass

    def _sync_loaded_id(self, ext: Dict[str, Any], loaded: Any):
        """Syncs the exact numeric source ID from the JVM sidecar response."""
        if not loaded or not isinstance(loaded, list):
            return
        pkg = ext.get("pkg", "").lower()
        name = ext.get("name", "").lower()
        for s in loaded:
            s_pkg = s.get("pkgName", "").lower()
            s_name = s.get("name", "").lower()
            if s_pkg == pkg or s_name == name:
                new_id = str(s.get("id"))
                ext["id"] = new_id
                logger.info(f"Updated extension '{ext.get('name')}' to JVM source ID: {new_id}")
                self._save_repos()
                break
