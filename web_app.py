from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


def runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


BASE_DIR = runtime_base_dir()
STATIC_DIR = BASE_DIR / "web" / "static"
INDEX_FILE = STATIC_DIR / "index.html"
BARK_URL_ENV = "VIDEO_MONITOR_BARK_URL"


class StartConfig(BaseModel):
    url: str
    browserChannel: str = "msedge"
    monitorInterval: float = 2.0
    autoLogin: bool = False
    loginPhone: Optional[str] = None
    loginPassword: Optional[str] = None
    loginPhoneSelector: Optional[str] = None
    loginPasswordSelector: Optional[str] = None
    loginSubmitSelector: Optional[str] = None
    loginRetryInterval: float = 8.0
    autoPlay: bool = True
    muteBeforeAutoPlay: bool = True
    playSequential: bool = True
    nextSelector: Optional[str] = "#prevNextFocusNext"
    noVideoNextDelay: float = 3.0
    playbackRate: Optional[float] = 2.0
    barkUrl: Optional[str] = None
    notifySectionComplete: bool = False
    notifyAllComplete: bool = False


class BarkTestRequest(BaseModel):
    barkUrl: str


class ProcessManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._logs: deque[dict[str, Any]] = deque(maxlen=2000)
        self._next_log_id = 1
        self._started_at: float | None = None
        self._exit_code: int | None = None
        self._command: list[str] | None = None
        self._pid: int | None = None
        self._paused = False

    def start(self, config: StartConfig) -> dict[str, Any]:
        normalized = self._normalize_config(config)

        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise HTTPException(status_code=409, detail="A monitor process is already running.")

            self._logs.clear()
            self._next_log_id = 1
            self._exit_code = None
            self._paused = False

            command = self._build_command(normalized)
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            if normalized.autoLogin:
                env["VIDEO_MONITOR_LOGIN_PHONE"] = normalized.loginPhone or ""
                env["VIDEO_MONITOR_LOGIN_PASSWORD"] = normalized.loginPassword or ""
            if normalized.barkUrl:
                env[BARK_URL_ENV] = normalized.barkUrl

            try:
                process = subprocess.Popen(
                    command,
                    cwd=BASE_DIR,
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except OSError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc

            self._process = process
            self._started_at = time.time()
            self._command = command
            self._pid = process.pid
            self._add_log("system", "Monitor started.")
            self._add_log("system", self._format_command(command))

            reader = threading.Thread(target=self._read_stdout, args=(process,), daemon=True)
            reader.start()

            return self.status()

    def pause(self) -> dict[str, Any]:
        self._send_control_command("pause")
        with self._lock:
            self._paused = True
        self._add_log("system", "Pause requested.")
        return self.status()

    def resume(self) -> dict[str, Any]:
        self._send_control_command("resume")
        with self._lock:
            self._paused = False
        self._add_log("system", "Resume requested.")
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            process = self._process

        if process is None or process.poll() is not None:
            return self.status()

        self._add_log("system", "Stopping monitor...")
        try:
            if process.stdin:
                process.stdin.write("stop\n")
                process.stdin.flush()
            process.wait(timeout=5)
        except (BrokenPipeError, OSError):
            pass
        except subprocess.TimeoutExpired:
            self._add_log("system", "Graceful stop timed out; terminating monitor.")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._add_log("system", "Terminate timed out; killing monitor.")
                process.kill()
                process.wait(timeout=5)

        with self._lock:
            self._paused = False

        return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self._process is not None and self._process.poll() is None
            return {
                "running": running,
                "paused": running and self._paused,
                "pid": self._pid if running else None,
                "startedAt": self._started_at,
                "exitCode": self._exit_code,
                "command": self._format_command(self._command) if self._command else None,
            }

    def logs_after(self, last_id: int) -> list[dict[str, Any]]:
        with self._lock:
            return [entry for entry in self._logs if entry["id"] > last_id]

    def export_logs(self) -> str:
        with self._lock:
            lines = [
                "Video Monitor Console Logs",
                f"Exported at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"Running: {self._process is not None and self._process.poll() is None}",
                "",
            ]
            lines.extend(
                f"[{entry['timestamp']}] {entry['stream']} {entry['line']}"
                for entry in self._logs
            )
            return "\n".join(lines) + "\n"

    def _send_control_command(self, command: str) -> None:
        with self._lock:
            process = self._process

        if process is None or process.poll() is not None:
            raise HTTPException(status_code=409, detail="No monitor process is running.")

        try:
            if not process.stdin:
                raise OSError("Monitor stdin is not available.")
            process.stdin.write(f"{command}\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    def _read_stdout(self, process: subprocess.Popen[str]) -> None:
        if process.stdout:
            for line in process.stdout:
                self._add_log("stdout", line.rstrip("\n"))

        return_code = process.wait()
        with self._lock:
            if self._process is process:
                self._process = None
                self._exit_code = return_code
                self._paused = False
        self._add_log("system", f"Monitor exited with code {return_code}.")

    def _add_log(self, stream: str, line: str) -> None:
        with self._lock:
            self._logs.append(
                {
                    "id": self._next_log_id,
                    "timestamp": time.strftime("%H:%M:%S"),
                    "stream": stream,
                    "line": line,
                }
            )
            self._next_log_id += 1

    def _normalize_config(self, config: StartConfig) -> StartConfig:
        config.url = config.url.strip()
        if not config.url:
            raise HTTPException(status_code=422, detail="URL is required.")
        if config.browserChannel == "chromium":
            config.browserChannel = "msedge"
        if config.browserChannel not in {"chrome", "msedge"}:
            raise HTTPException(status_code=422, detail="Unsupported browser channel.")
        if config.monitorInterval <= 0:
            raise HTTPException(status_code=422, detail="Monitor interval must be greater than 0.")
        if config.loginRetryInterval < 0:
            raise HTTPException(status_code=422, detail="Login retry interval must be 0 or greater.")
        if config.noVideoNextDelay < 0:
            raise HTTPException(status_code=422, detail="No-video next delay must be 0 or greater.")
        if config.playbackRate is not None and config.playbackRate <= 0:
            raise HTTPException(status_code=422, detail="Playback rate must be greater than 0.")
        if config.playSequential and not config.autoPlay:
            raise HTTPException(status_code=422, detail="Sequential playback requires auto-play.")
        if config.autoLogin:
            config.loginPhone = (config.loginPhone or "").strip()
            if not config.loginPhone:
                raise HTTPException(status_code=422, detail="Login phone is required when auto-login is enabled.")
            if not config.loginPassword:
                raise HTTPException(status_code=422, detail="Login password is required when auto-login is enabled.")
        else:
            config.loginPhone = None
            config.loginPassword = None

        if config.loginPhoneSelector is not None:
            config.loginPhoneSelector = config.loginPhoneSelector.strip() or None
        if config.loginPasswordSelector is not None:
            config.loginPasswordSelector = config.loginPasswordSelector.strip() or None
        if config.loginSubmitSelector is not None:
            config.loginSubmitSelector = config.loginSubmitSelector.strip() or None

        if config.nextSelector is not None:
            config.nextSelector = config.nextSelector.strip() or None
        if config.barkUrl is not None:
            config.barkUrl = config.barkUrl.strip() or None
        if (config.notifySectionComplete or config.notifyAllComplete) and not config.barkUrl:
            raise HTTPException(status_code=422, detail="Bark key or URL is required when notifications are enabled.")
        if not (config.notifySectionComplete or config.notifyAllComplete):
            config.barkUrl = None

        return config

    def _build_command(self, config: StartConfig) -> list[str]:
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--worker"]
        else:
            command = [sys.executable, "-u", str(BASE_DIR / "main.py")]

        command.extend(
            [
                "--url",
                config.url,
                "--browser-channel",
                config.browserChannel,
                "--monitor-interval",
                str(config.monitorInterval),
                "--no-video-next-delay",
                str(config.noVideoNextDelay),
            ]
        )

        if config.autoLogin:
            command.append("--auto-login")
            command.extend(["--login-retry-interval", str(config.loginRetryInterval)])
            if config.loginPhoneSelector:
                command.extend(["--login-phone-selector", config.loginPhoneSelector])
            if config.loginPasswordSelector:
                command.extend(["--login-password-selector", config.loginPasswordSelector])
            if config.loginSubmitSelector:
                command.extend(["--login-submit-selector", config.loginSubmitSelector])
        if config.autoPlay:
            command.append("--auto-play")
        if config.muteBeforeAutoPlay:
            command.append("--mute-before-auto-play")
        if config.playSequential:
            command.append("--play-sequential")
        if config.nextSelector:
            command.extend(["--next-selector", config.nextSelector])
        if config.playbackRate is not None:
            command.extend(["--playback-rate", str(config.playbackRate)])
        if config.notifySectionComplete:
            command.append("--notify-section-complete")
        if config.notifyAllComplete:
            command.append("--notify-all-complete")

        return command

    def _format_command(self, command: list[str] | None) -> str | None:
        if command is None:
            return None
        return " ".join(self._quote(part) for part in command)

    def _quote(self, value: str) -> str:
        if value == "":
            return "''"
        if all(char.isalnum() or char in "-_./:=#?" for char in value):
            return value
        return "'" + value.replace("'", "'\"'\"'") + "'"


def normalize_bark_url(value: str | None) -> str | None:
    if not value:
        return None

    value = value.strip().rstrip("/")
    if not value:
        return None

    if value.startswith(("http://", "https://")):
        return value

    return f"https://api.day.app/{urllib.parse.quote(value.strip('/'), safe='')}"


def build_bark_push_url(bark_url: str, title: str, body: str) -> str:
    parsed = urllib.parse.urlsplit(bark_url.rstrip("/"))
    path = (
        f"{parsed.path.rstrip('/')}/"
        f"{urllib.parse.quote(title, safe='')}/"
        f"{urllib.parse.quote(body, safe='')}"
    )
    query = parsed.query
    archive_query = urllib.parse.urlencode({"isArchive": "1"})
    if query:
        query = f"{query}&{archive_query}"
    else:
        query = archive_query

    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, query, parsed.fragment)
    )


def send_bark_test_notification(bark_url: str) -> dict[str, Any]:
    normalized_url = normalize_bark_url(bark_url)
    if not normalized_url:
        raise HTTPException(status_code=422, detail="Bark key or URL is required.")

    title = "视频控制台：测试推送"
    body = f"Bark 测试推送成功。\n{time.strftime('%Y-%m-%d %H:%M:%S')}"
    push_url = build_bark_push_url(normalized_url, title, body)
    request = urllib.request.Request(
        push_url,
        headers={"User-Agent": "video-monitor-console/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            response_body = response.read(2048).decode("utf-8", errors="replace")
            return {
                "action": "sent",
                "statusCode": response.status,
                "message": "Bark test notification sent.",
                "response": response_body,
            }
    except urllib.error.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Bark returned HTTP {exc.code}: {exc.reason}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


manager = ProcessManager()
app = FastAPI(title="Video Monitor Console")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_FILE)


@app.head("/")
def index_head() -> Response:
    return Response(status_code=200)


@app.get("/api/status")
def status() -> dict[str, Any]:
    return manager.status()


@app.post("/api/start")
def start(config: StartConfig) -> dict[str, Any]:
    return manager.start(config)


@app.post("/api/pause")
def pause() -> dict[str, Any]:
    return manager.pause()


@app.post("/api/resume")
def resume() -> dict[str, Any]:
    return manager.resume()


@app.post("/api/stop")
def stop() -> dict[str, Any]:
    return manager.stop()


@app.get("/api/logs/export")
def export_logs() -> Response:
    filename = f"video-monitor-logs-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    return Response(
        content=manager.export_logs(),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/bark/test")
def test_bark(request: BarkTestRequest) -> dict[str, Any]:
    return send_bark_test_notification(request.barkUrl)


@app.get("/api/logs")
async def logs(after: int = Query(default=0, ge=0)) -> StreamingResponse:
    async def event_stream():
        last_id = after
        last_status_sent = 0.0

        while True:
            for entry in manager.logs_after(last_id):
                last_id = entry["id"]
                yield "event: log\n"
                yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"

            now = time.monotonic()
            if now - last_status_sent >= 1:
                yield "event: status\n"
                yield f"data: {json.dumps(manager.status(), ensure_ascii=False)}\n\n"
                last_status_sent = now

            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
