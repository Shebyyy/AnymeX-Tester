import asyncio
import collections
import json
import logging
import os
from typing import Any, Dict, List, Optional
from runtime.log_manager import log_manager

logger = logging.getLogger("SidecarBridge")


class SidecarBridge:
    _instance: Optional["SidecarBridge"] = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, jar_path: str = "data/tools/anymex_desktop_runtime.jar"):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self.jar_path = os.path.abspath(jar_path)
        self.process: Optional[asyncio.subprocess.Process] = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._request_counter = 0
        self._is_ready = False
        self._read_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._recent_logs: collections.deque = collections.deque(maxlen=200)
        self._initialized = True

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None and self._is_ready

    def get_recent_logs(self, count: int = 15) -> List[str]:
        return list(self._recent_logs)[-count:]

    async def start(self) -> bool:
        if self.is_running:
            return True

        if not os.path.exists(self.jar_path):
            logger.error(f"Cannot start SidecarBridge: JAR not found at {self.jar_path}")
            return False

        logger.info(f"Starting Sidecar process: java -jar {self.jar_path}")
        try:
            self.process = await asyncio.create_subprocess_exec(
                "java",
                "-Dfile.encoding=UTF-8",
                "-Dsun.stdout.encoding=UTF-8",
                "-Dsun.stderr.encoding=UTF-8",
                "-Xms128m",
                "-Xmx512m",
                "-noverify",
                "-jar",
                self.jar_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=32 * 1024 * 1024,  # 32 MB line buffer
            )

            ready_event = asyncio.Event()
            self._read_task = asyncio.create_task(self._stdout_loop())
            self._stderr_task = asyncio.create_task(self._stderr_loop(ready_event))

            try:
                await asyncio.wait_for(ready_event.wait(), timeout=20.0)
                self._is_ready = True
                logger.info("Sidecar process successfully started and ready!")
                return True
            except asyncio.TimeoutError:
                logger.warning("Sidecar startup message timed out, assuming running...")
                self._is_ready = True
                return True

        except Exception as e:
            logger.error(f"Failed to start sidecar bridge: {e}")
            self.stop()
            return False

    async def _stdout_loop(self):
        while self.process and self.process.stdout and not self.process.stdout.at_eof():
            try:
                line_bytes = await self.process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    payload = json.loads(line)
                    req_id = payload.get("id")
                    if req_id is not None:
                        req_id = str(req_id)
                    data = payload.get("data")
                    status = payload.get("status")
                    raw_err = payload.get("error")

                    if req_id and req_id in self._pending_requests:
                        future = self._pending_requests.pop(req_id)
                        if not future.done():
                            if status == "error" or raw_err:
                                err_details = str(raw_err or data or "Unknown sidecar error")
                                recent = self.get_recent_logs(8)
                                if recent:
                                    err_details += "\n" + "\n".join(recent[-5:])
                                future.set_exception(RuntimeError(err_details))
                            else:
                                future.set_result(data)
                    elif raw_err and self._pending_requests:
                        # JAR threw an unhandled exception without returning request id
                        err_details = str(raw_err)
                        recent = self.get_recent_logs(8)
                        if recent:
                            err_details += "\n" + "\n".join(recent[-5:])
                        # Fail the oldest active request immediately to prevent fake timeouts
                        first_key = next(iter(self._pending_requests))
                        future = self._pending_requests.pop(first_key)
                        if not future.done():
                            future.set_exception(RuntimeError(err_details))
                    else:
                        # Non-request JSON output from JAR
                        log_manager.record_jar_log(line, is_stderr=False)
                except json.JSONDecodeError:
                    self._recent_logs.append(f"[OUT] {line}")
                    log_manager.record_jar_log(line, is_stderr=False)
                    logger.debug(f"[Sidecar Raw Out] {line}")
            except Exception as e:
                logger.error(f"Error in stdout loop: {e}")
                await asyncio.sleep(0.1)

    async def _stderr_loop(self, ready_event: asyncio.Event):
        while self.process and self.process.stderr and not self.process.stderr.at_eof():
            try:
                line_bytes = await self.process.stderr.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                self._recent_logs.append(line)
                log_manager.record_jar_log(line, is_stderr=True)
                logger.debug(f"[Sidecar Log] {line}")
                if "AnymeX Sidecar Process Started" in line or "Started" in line:
                    ready_event.set()
            except Exception as e:
                logger.error(f"Error in stderr loop: {e}")
                break

    async def invoke_method(self, method: str, args: Dict[str, Any], timeout: float = 60.0) -> Any:
        if not self.is_running:
            started = await self.start()
            if not started:
                raise RuntimeError("Sidecar is not running and failed to start.")

        self._request_counter += 1
        req_id = str(self._request_counter)
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[req_id] = future

        message = {
            "method": method,
            "args": args,
            "id": req_id,
        }

        logger.info(f"RPC -> {method} (id={req_id})")
        encoded = (json.dumps(message) + "\n").encode("utf-8")
        if self.process and self.process.stdin:
            self.process.stdin.write(encoded)
            await self.process.stdin.drain()
        else:
            self._pending_requests.pop(req_id, None)
            raise RuntimeError("Sidecar stdin is not available.")

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            # Send cancel to JVM sidecar to release hung OkHttp calls / threads
            try:
                if self.process and self.process.stdin:
                    cancel_msg = (json.dumps({"method": "cancel", "args": {"id": req_id}}) + "\n").encode("utf-8")
                    self.process.stdin.write(cancel_msg)
                    await self.process.stdin.drain()
            except Exception:
                pass

            recent = self.get_recent_logs(8)
            err_msg = f"JAR method '{method}' timed out after {timeout}s"
            if recent:
                err_msg += "\n" + "\n".join(recent[-4:])
            raise TimeoutError(err_msg)

    def stop(self):
        self._is_ready = False
        if self._read_task:
            self._read_task.cancel()
        if self._stderr_task:
            self._stderr_task.cancel()
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
            self.process = None
        for f in self._pending_requests.values():
            if not f.done():
                f.set_exception(RuntimeError("Sidecar stopped"))
        self._pending_requests.clear()
        logger.info("SidecarBridge stopped.")
