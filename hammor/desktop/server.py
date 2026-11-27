"""Hammor Co. desktop app: a small local web server plus an app window.

    python -m hammor.desktop            # start and open the office window
    python -m hammor.desktop --selftest # check the app starts, then exit

The window shows the six team members around a meeting table. It can:
  * replay a morning meeting that GitHub held and saved to reports/latest.json
  * hold a LIVE meeting on this computer (needs a Claude API key, about US$1–2 each)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("hammor.desktop")

PORT = 8765
DEFAULT_REPO = "albateen11/Khalid-"
DEFAULT_BRANCH = "claude/hammor-stock-analysis-uae-cccy7x"
IDLE_EXIT_SECONDS = 15 * 60  # quit when the window has been closed this long


def resource(name: str, folder: str = "hammor/desktop") -> Path:
    """Path to a bundled file, both from source and inside the PyInstaller .exe."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / folder / name


WEB_FILES = {"/manifest.webmanifest": "application/manifest+json",
             "/icon-192.png": "image/png", "/icon-512.png": "image/png"}


def app_dir() -> Path:
    root = os.environ.get("APPDATA") or str(Path.home() / ".config")
    d = Path(root) / "HammorCo"
    (d / "meetings").mkdir(parents=True, exist_ok=True)
    return d


# ------------------------------------------------------------------ settings

def load_settings() -> dict:
    p = app_dir() / "settings.json"
    s = {"anthropic_key": "", "github_token": "", "repo": DEFAULT_REPO, "branch": DEFAULT_BRANCH}
    try:
        s.update(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return s


def save_settings(update: dict) -> dict:
    s = load_settings()
    for k in ("anthropic_key", "github_token", "repo", "branch"):
        v = update.get(k)
        if isinstance(v, str) and v.strip():
            s[k] = v.strip()
    for k in update.get("clear", []):
        if k in ("anthropic_key", "github_token"):
            s[k] = ""
    (app_dir() / "settings.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    return s


def public_settings() -> dict:
    s = load_settings()
    return {"has_anthropic_key": bool(s["anthropic_key"] or os.environ.get("ANTHROPIC_API_KEY")),
            "has_github_token": bool(s["github_token"]), "repo": s["repo"], "branch": s["branch"]}


# --------------------------------------------------------- meetings from GitHub

def _github_get(path: str, raw: bool = True):
    s = load_settings()
    url = f"https://api.github.com/repos/{s['repo']}/contents/{path}?ref={s['branch']}"
    headers = {"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
               "User-Agent": "HammorCo-Desktop"}
    if s["github_token"]:
        headers["Authorization"] = f"Bearer {s['github_token']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _local_meetings() -> list[Path]:
    return sorted((app_dir() / "meetings").glob("*.json"), reverse=True)


def latest_meeting(date: str | None = None) -> dict | None:
    """The GitHub meeting for `date` (default: the latest), else the newest local one."""
    name = f"reports/{date}.json" if date else "reports/latest.json"
    try:
        rec = _github_get(name)
        rec["_source"] = "github"
        app_dir().joinpath("meetings", f"{rec['date']}-github.json").write_text(
            json.dumps(rec, ensure_ascii=False), encoding="utf-8")  # offline copy
        return rec
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        log.info("GitHub meeting unavailable (%s); trying local copies", e)
    for p in _local_meetings():
        if date and not p.name.startswith(date):
            continue
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
            rec["_source"] = "local"
            return rec
        except (OSError, ValueError):
            continue
    return None


def history() -> list[str]:
    dates = set()
    try:
        for item in _github_get("reports", raw=False):
            n = item.get("name", "")
            if n.endswith(".json") and n[:4].isdigit():
                dates.add(n[:10])
    except (urllib.error.URLError, OSError, ValueError):
        pass
    dates |= {p.name[:10] for p in _local_meetings()}
    return sorted(dates, reverse=True)[:60]


# --------------------------------------------------------------- live meeting

class LiveSession:
    def __init__(self):
        self.events: list[dict] = []
        self.cond = threading.Condition()
        self.running = False

    def emit(self, event: dict) -> None:
        with self.cond:
            event = {**event, "seq": len(self.events)}
            self.events.append(event)
            self.cond.notify_all()

    def start(self, api_key: str) -> bool:
        with self.cond:
            if self.running:
                return False
            self.running, self.events = True, []
        threading.Thread(target=self._run, args=(api_key,), daemon=True).start()
        return True

    def _run(self, api_key: str) -> None:
        from .. import main as pipeline  # heavy imports only when needed
        os.environ["ANTHROPIC_API_KEY"] = api_key
        try:
            self.emit({"type": "begin", "at": datetime.now().isoformat(timespec="seconds")})
            record = pipeline.run_pipeline(on_event=self.emit)
            data = json.loads(pipeline.meeting_json(record))
            data["_source"] = "live"
            stamp = datetime.now().strftime("%H%M")
            (app_dir() / "meetings" / f"{data['date']}-live-{stamp}.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8")
            self.emit({"type": "done", "record": data})
        except Exception as e:  # report to the window instead of dying silently
            log.exception("Live meeting failed")
            self.emit({"type": "error", "text": str(e)})
        finally:
            with self.cond:
                self.running = False
                self.cond.notify_all()


LIVE = LiveSession()
LAST_PING = [time.time()]


# -------------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    server_version = "HammorCo"

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)

    def _json(self, obj, status=HTTPStatus.OK):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def do_GET(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        LAST_PING[0] = time.time()
        if url.path in ("/", "/index.html"):
            body = resource("office.html").read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path in WEB_FILES:
            f = resource(url.path.lstrip("/"), "web")
            body = f.read_bytes() if f.exists() else b""
            self.send_response(HTTPStatus.OK if body else HTTPStatus.NOT_FOUND)
            self.send_header("Content-Type", WEB_FILES[url.path])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/api/ping":
            self._json({"ok": True, "app": "hammor"})
        elif url.path == "/api/settings":
            self._json(public_settings())
        elif url.path == "/api/latest":
            rec = latest_meeting((q.get("date") or [None])[0])
            self._json({"record": rec})
        elif url.path == "/api/history":
            self._json({"dates": history()})
        elif url.path == "/api/live/status":
            self._json({"running": LIVE.running, "events": len(LIVE.events)})
        elif url.path == "/api/live/events":
            self._sse(int((q.get("from") or ["0"])[0]))
        else:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        url = urlparse(self.path)
        LAST_PING[0] = time.time()
        if url.path == "/api/settings":
            save_settings(self._body())
            self._json(public_settings())
        elif url.path == "/api/live/start":
            key = load_settings()["anthropic_key"] or os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                self._json({"error": "Add your Claude API key in Settings first."},
                           HTTPStatus.BAD_REQUEST)
            elif not LIVE.start(key):
                self._json({"error": "A live meeting is already running."}, HTTPStatus.CONFLICT)
            else:
                self._json({"ok": True})
        else:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _sse(self, start: int):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        i = start
        try:
            while True:
                with LIVE.cond:
                    if i >= len(LIVE.events) and LIVE.running:
                        LIVE.cond.wait(timeout=15)
                    batch = LIVE.events[i:]
                    running = LIVE.running
                for ev in batch:
                    self.wfile.write(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode())
                i += len(batch)
                if not batch:
                    self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
                LAST_PING[0] = time.time()
                if not running and i >= len(LIVE.events):
                    return
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


# --------------------------------------------------------------- app window

def open_window(url: str) -> None:
    """Open the office in an Edge app window (no tabs or address bar) when possible."""
    candidates = [
        shutil.which("msedge"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        shutil.which("chrome"), shutil.which("google-chrome"),
    ]
    for exe in candidates:
        if exe and Path(exe).exists():
            try:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1440,920",
                                  f"--user-data-dir={app_dir() / 'window'}"])
                return
            except OSError:
                continue
    webbrowser.open(url)


def _already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=2) as r:
            return json.loads(r.read()).get("app") == "hammor"
    except (OSError, ValueError):
        return False


def _watchdog(server: ThreadingHTTPServer) -> None:
    while True:
        time.sleep(30)
        if not LIVE.running and time.time() - LAST_PING[0] > IDLE_EXIT_SECONDS:
            log.info("Window closed; shutting down")
            server.shutdown()
            return


def serve(port: int = PORT, open_browser: bool = True) -> None:
    url = f"http://127.0.0.1:{port}/"
    if _already_running(port):
        open_window(url)
        return
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=_watchdog, args=(server,), daemon=True).start()
    if open_browser:
        threading.Timer(0.5, open_window, args=(url,)).start()
    log.info("Hammor Co. office running at %s", url)
    server.serve_forever()


def selftest() -> int:
    import anthropic  # noqa: F401  (checks the bundle contains everything)
    import pandas  # noqa: F401
    import yfinance  # noqa: F401

    from .. import main as _main  # noqa: F401
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
            assert b"Hammor" in r.read()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/settings", timeout=5) as r:
            assert "repo" in json.loads(r.read())
    finally:
        server.shutdown()
    if sys.stdout:
        print("Hammor Co. desktop self-test OK")
    return 0


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="HammorCo")
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args(argv)
    handlers = [logging.FileHandler(app_dir() / "hammor.log", encoding="utf-8")]
    if sys.stderr:  # the windowless .exe has no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=handlers)
    if a.selftest:
        try:
            code = selftest()
        except Exception:  # never show an error dialog during automated checks
            log.exception("Self-test failed")
            code = 1
        sys.exit(code)
    serve(a.port, not a.no_browser)
