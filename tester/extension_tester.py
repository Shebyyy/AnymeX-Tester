import aiohttp
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from runtime.sidecar import SidecarBridge

logger = logging.getLogger("ExtensionTester")

@dataclass
class StepResult:
    name: str
    passed: bool = False
    duration_ms: int = 0
    info: str = ""
    error: Optional[str] = None
    data: Any = None

@dataclass
class VideoStreamHealth:
    quality: str
    url: str
    alive: bool
    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None

@dataclass
class TestReport:
    extension_name: str
    extension_pkg: str
    backend: str
    item_type: str
    query: str
    overall_passed: bool = False
    total_duration_ms: int = 0
    search_step: Optional[StepResult] = None
    detail_step: Optional[StepResult] = None
    content_step: Optional[StepResult] = None
    video_streams: List[VideoStreamHealth] = field(default_factory=list)
    page_count: int = 0
    novel_snippet: str = ""
    log_content: str = ""

class ExtensionTester:
    def __init__(self):
        self.bridge = SidecarBridge()

    async def _check_stream_url(self, url: str, headers: Optional[Dict[str, str]] = None) -> (bool, int, Optional[str]):
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Range": "bytes=0-1024"
        }
        if headers and isinstance(headers, dict):
            req_headers.update(headers)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=req_headers, timeout=aiohttp.ClientTimeout(total=15), allow_redirects=True) as resp:
                    alive = resp.status in (200, 206)
                    return alive, resp.status, None if alive else f"HTTP {resp.status}"
        except Exception as e:
            return False, 0, str(e)

    async def run_test(self, extension: Dict[str, Any], query: str) -> TestReport:
        report = TestReport(
            extension_name=extension.get("name", "Unknown"),
            extension_pkg=extension.get("pkg", "unknown"),
            backend=extension.get("backend", "unknown"),
            item_type=extension.get("itemType", "anime"),
            query=query
        )

        source_id = str(extension.get("id", extension.get("pkg")))
        is_anime = report.item_type == "anime"
        total_start = time.perf_counter()

        logger.info(f"=== Starting Test Pipeline for '{report.extension_name}' (ID: {source_id}, Backend: {report.backend}, Type: {report.item_type}) ===")

        # Step 1: Search
        search_start = time.perf_counter()
        search_res = StepResult(name="Search")
        first_item = None

        try:
            logger.info(f"[Step 1] Invoking search (sourceId={source_id}, query='{query}', isAnime={is_anime})...")
            res = await self.bridge.invoke_method("search", {
                "sourceId": source_id,
                "isAnime": is_anime,
                "query": query,
                "page": 1,
                "filters": []
            }, timeout=60.0)

            search_res.duration_ms = int((time.perf_counter() - search_start) * 1000)
            items = res.get("list", []) if isinstance(res, dict) else (res if isinstance(res, list) else [])

            if items and len(items) > 0:
                first_item = items[0]
                search_res.passed = True
                search_res.info = f"Found {len(items)} items. Selected: '{first_item.get('title', 'Unknown')}'"
                search_res.data = first_item
                logger.info(f"[Step 1 Passed] {search_res.info} in {search_res.duration_ms}ms")
            else:
                logger.warning(f"[Step 1] Search returned 0 items for '{query}', falling back to getPopular...")
                pop_res = await self.bridge.invoke_method("getPopular", {
                    "sourceId": source_id,
                    "isAnime": is_anime,
                    "page": 1
                }, timeout=45.0)
                pop_items = pop_res.get("list", []) if isinstance(pop_res, dict) else []
                if pop_items:
                    first_item = pop_items[0]
                    search_res.passed = True
                    search_res.info = f"No search results for '{query}', but Popular list active! Selected: '{first_item.get('title', 'Unknown')}'"
                    search_res.data = first_item
                    logger.info(f"[Step 1 Passed] {search_res.info}")
                else:
                    search_res.passed = False
                    search_res.error = f"Search returned 0 results for '{query}' and Popular list was empty."
                    logger.warning(f"[Step 1 Failed] {search_res.error}")
        except Exception as e:
            search_res.duration_ms = int((time.perf_counter() - search_start) * 1000)
            search_res.passed = False
            search_res.error = str(e)
            logger.error(f"[Step 1 Exception] {e}")

        report.search_step = search_res
        if not search_res.passed or not first_item:
            report.total_duration_ms = int((time.perf_counter() - total_start) * 1000)
            return report

        # Step 2: Details & Episodes
        detail_start = time.perf_counter()
        detail_res = StepResult(name="Details & Episodes")
        detailed_media = None
        first_episode = None

        try:
            media_payload = {
                "title": first_item.get("title", ""),
                "url": first_item.get("url", ""),
                "thumbnail_url": first_item.get("cover", first_item.get("thumbnail_url", "")),
                "description": first_item.get("description", ""),
                "author": first_item.get("author", ""),
                "artist": first_item.get("artist", ""),
                "genre": first_item.get("genre", [])
            }

            logger.info(f"[Step 2] Invoking getDetail for media '{first_item.get('title')}' (url={first_item.get('url')})...")
            detailed_media = await self.bridge.invoke_method("getDetail", {
                "sourceId": source_id,
                "isAnime": is_anime,
                "media": media_payload
            }, timeout=60.0)

            detail_res.duration_ms = int((time.perf_counter() - detail_start) * 1000)
            episodes = detailed_media.get("episodes", []) if isinstance(detailed_media, dict) else []

            if episodes and len(episodes) > 0:
                first_episode = episodes[0]
                detail_res.passed = True
                ep_label = "episodes" if is_anime else "chapters"
                detail_res.info = f"Fetched {len(episodes)} {ep_label}. Selected: '{first_episode.get('name', 'Episode 1')}'"
                detail_res.data = detailed_media
                logger.info(f"[Step 2 Passed] {detail_res.info} in {detail_res.duration_ms}ms")
            else:
                detail_res.passed = False
                detail_res.error = "Details loaded, but episode/chapter list was empty."
                logger.warning(f"[Step 2 Failed] {detail_res.error}")
        except Exception as e:
            detail_res.duration_ms = int((time.perf_counter() - detail_start) * 1000)
            detail_res.passed = False
            detail_res.error = str(e)
            logger.error(f"[Step 2 Exception] {e}")

        report.detail_step = detail_res
        if not detail_res.passed or not first_episode:
            report.total_duration_ms = int((time.perf_counter() - total_start) * 1000)
            return report

        # Step 3: Stream / Content Extraction
        content_start = time.perf_counter()
        content_res = StepResult(name="Content Extraction")

        try:
            if is_anime:
                # Video List
                episode_payload = {
                    "name": first_episode.get("name", ""),
                    "url": first_episode.get("url", ""),
                    "date_upload": first_episode.get("date_upload", ""),
                    "description": first_episode.get("description", ""),
                    "episode_number": str(first_episode.get("episode_number", "1")),
                    "scanlator": first_episode.get("scanlator", "")
                }
                logger.info(f"[Step 3] Invoking getVideoList for episode '{first_episode.get('name')}' (url={first_episode.get('url')})...")
                videos = await self.bridge.invoke_method("getVideoList", {
                    "sourceId": source_id,
                    "isAnime": True,
                    "episode": episode_payload
                }, timeout=75.0)

                content_res.duration_ms = int((time.perf_counter() - content_start) * 1000)

                if videos and isinstance(videos, list) and len(videos) > 0:
                    stream_checks = []
                    for v in videos[:4]:  # Check top 4 qualities
                        v_url = v.get("url", "")
                        v_quality = v.get("quality", "Default")
                        v_headers = v.get("headers", {})
                        if v_url:
                            stream_checks.append((v_quality, v_url, v_headers))

                    checked_streams = []
                    for quality, v_url, v_headers in stream_checks:
                        alive, status, err = await self._check_stream_url(v_url, v_headers)
                        checked_streams.append(VideoStreamHealth(
                            quality=quality,
                            url=v_url,
                            alive=alive,
                            status_code=status,
                            headers=v_headers if isinstance(v_headers, dict) else {},
                            error=err
                        ))

                    report.video_streams = checked_streams
                    alive_count = sum(1 for s in checked_streams if s.alive)

                    if alive_count > 0:
                        content_res.passed = True
                        content_res.info = f"Found {len(videos)} streams ({alive_count}/{len(checked_streams)} verified live)."
                        logger.info(f"[Step 3 Passed] {content_res.info} in {content_res.duration_ms}ms")
                    else:
                        content_res.passed = False
                        content_res.error = f"Found {len(videos)} streams, but none returned 200/206 OK."
                        logger.warning(f"[Step 3 Failed] {content_res.error}")
                else:
                    content_res.passed = False
                    content_res.error = "No video streams returned for episode."
                    logger.warning(f"[Step 3 Failed] {content_res.error}")

            elif report.item_type == "manga":
                # Page List
                episode_payload = {
                    "name": first_episode.get("name", ""),
                    "url": first_episode.get("url", "")
                }
                logger.info(f"[Step 3] Invoking getPageList for chapter '{first_episode.get('name')}' (url={first_episode.get('url')})...")
                pages = await self.bridge.invoke_method("getPageList", {
                    "sourceId": source_id,
                    "isAnime": False,
                    "episode": episode_payload
                }, timeout=60.0)

                content_res.duration_ms = int((time.perf_counter() - content_start) * 1000)
                if pages and isinstance(pages, list) and len(pages) > 0:
                    report.page_count = len(pages)
                    p1_url = pages[0].get("url") if isinstance(pages[0], dict) else str(pages[0])
                    alive, status, err = await self._check_stream_url(p1_url)
                    if alive:
                        content_res.passed = True
                        content_res.info = f"Found {len(pages)} pages (Page 1 verified HTTP {status})."
                        logger.info(f"[Step 3 Passed] {content_res.info} in {content_res.duration_ms}ms")
                    else:
                        content_res.passed = False
                        content_res.error = f"Extracted {len(pages)} pages, but Page 1 failed ({err})."
                        logger.warning(f"[Step 3 Failed] {content_res.error}")
                else:
                    content_res.passed = False
                    content_res.error = "No manga pages returned."
                    logger.warning(f"[Step 3 Failed] {content_res.error}")

            else:
                # Novel Content
                logger.info(f"[Step 3] Invoking getNovelContent for chapter '{first_episode.get('name')}' (url={first_episode.get('url')})...")
                novel_text = await self.bridge.invoke_method("getNovelContent", {
                    "sourceId": source_id,
                    "chapterTitle": first_episode.get("name", ""),
                    "chapterUrl": first_episode.get("url", "")
                }, timeout=50.0)

                content_res.duration_ms = int((time.perf_counter() - content_start) * 1000)
                if novel_text and isinstance(novel_text, str) and len(novel_text.strip()) > 50:
                    report.novel_snippet = novel_text.strip()[:200]
                    content_res.passed = True
                    content_res.info = f"Extracted {len(novel_text)} chars of text."
                    logger.info(f"[Step 3 Passed] {content_res.info} in {content_res.duration_ms}ms")
                else:
                    content_res.passed = False
                    content_res.error = "Novel content was empty or under 50 characters."
                    logger.warning(f"[Step 3 Failed] {content_res.error}")

        except Exception as e:
            content_res.duration_ms = int((time.perf_counter() - content_start) * 1000)
            content_res.passed = False
            content_res.error = str(e)
            logger.error(f"[Step 3 Exception] {e}")

        report.content_step = content_res
        report.overall_passed = bool(
            report.search_step and report.search_step.passed and
            report.detail_step and report.detail_step.passed and
            report.content_step and report.content_step.passed
        )
        report.total_duration_ms = int((time.perf_counter() - total_start) * 1000)
        logger.info(f"=== Test Finished: {'PASSED' if report.overall_passed else 'FAILED'} ({report.total_duration_ms}ms) ===")
        return report
