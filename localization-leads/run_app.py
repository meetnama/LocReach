"""
LocReach launcher — mirrors Emails_Tool's browser-watchdog pattern.

Starts Streamlit, opens Chrome when ready, and exits (killing Streamlit)
when the browser tab stops sending heartbeats OR signals /closing.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

STREAMLIT_PORT = 8501
HEARTBEAT_PORT = 8502
# Must exceed Chrome's background-tab timer throttle (~60s) and any long
# Streamlit rerender. Heartbeat now runs on window.parent so iframe remounts
# during Step 1 auto-refresh no longer drop pings — this is belt-and-suspenders.
SHUTDOWN_TIMEOUT = 180
STARTUP_GRACE = 90

_last_heartbeat = time.time()
_got_heartbeat = False
_heartbeat_lock = threading.Lock()
_streamlit_proc: subprocess.Popen | None = None
_shutting_down = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "run_app.log")


def _log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"[run_app {ts}] {msg}", flush=True)
    except Exception:
        pass


def _setup_logging() -> None:
    """Redirect stdout/stderr to a log file.

    Required when launched via pythonw.exe (no console), which has no
    stdout/stderr handles at all — writing to them would raise.
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    old_path = LOG_PATH + ".old"
    try:
        if os.path.exists(old_path):
            os.remove(old_path)
        if os.path.exists(LOG_PATH):
            os.replace(LOG_PATH, old_path)
    except OSError:
        pass
    log_file = open(LOG_PATH, "w", encoding="utf-8", buffering=1)
    sys.stdout = log_file
    sys.stderr = log_file


class _HeartbeatHandler(BaseHTTPRequestHandler):
    def _accept(self) -> None:
        global _last_heartbeat, _got_heartbeat
        with _heartbeat_lock:
            _last_heartbeat = time.time()
            _got_heartbeat = True
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:
        path = self.path.rstrip("/")
        if path == "/heartbeat":
            self._accept()
        elif path == "/closing":
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            _log("shutdown requested via /closing (browser tab close beacon)")
            threading.Thread(target=_shutdown, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args) -> None:
        pass


def _heartbeat_server() -> None:
    server = HTTPServer(("127.0.0.1", HEARTBEAT_PORT), _HeartbeatHandler)
    _log(f"heartbeat server listening on 127.0.0.1:{HEARTBEAT_PORT}")
    server.serve_forever()


def _watchdog() -> None:
    while True:
        time.sleep(1)
        with _heartbeat_lock:
            quiet = time.time() - _last_heartbeat
            got = _got_heartbeat
        limit = SHUTDOWN_TIMEOUT if got else STARTUP_GRACE
        if quiet > limit:
            _log(
                f"shutdown via heartbeat timeout "
                f"(quiet={quiet:.1f}s limit={limit}s got_heartbeat={got})"
            )
            _shutdown()


def _kill_process_tree(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
        )
    else:
        import signal

        os.kill(pid, signal.SIGTERM)


def _shutdown() -> None:
    global _streamlit_proc, _shutting_down
    if _shutting_down:
        return
    _shutting_down = True
    if _streamlit_proc and _streamlit_proc.poll() is None:
        _log(f"killing Streamlit pid={_streamlit_proc.pid}")
        _kill_process_tree(_streamlit_proc.pid)
    os._exit(0)


def _find_chrome() -> str | None:
    try:
        import winreg

        for key in [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        ]:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
                    path = winreg.QueryValue(k, None)
                    if path and os.path.exists(path):
                        return path
            except OSError:
                pass
    except ImportError:
        pass
    for path in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]:
        if os.path.exists(path):
            return path
    return None


def _open_browser_when_ready() -> None:
    if os.environ.get("LOCREACH_NO_BROWSER"):
        return
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", STREAMLIT_PORT), timeout=0.5):
                break
        except OSError:
            time.sleep(0.5)
    url = f"http://localhost:{STREAMLIT_PORT}"
    chrome = _find_chrome()
    if chrome:
        try:
            subprocess.Popen(
                [chrome, "--new-window", url],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return
        except OSError:
            pass
    try:
        os.startfile(url)  # type: ignore[attr-defined]
        return
    except OSError:
        pass
    try:
        import webbrowser

        webbrowser.open_new(url)
    except OSError:
        pass


def _wait_for_free_port(port: int, attempts: int = 40) -> None:
    for _ in range(attempts):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", port))
            sock.close()
            return
        except OSError:
            sock.close()
            time.sleep(0.25)


def _venv_python() -> str:
    """Resolve the venv's real python.exe, even when this script itself is
    launched via pythonw.exe (sys.executable would then point at pythonw)."""
    candidate = os.path.join(os.path.dirname(sys.executable), "python.exe")
    return candidate if os.path.exists(candidate) else sys.executable


def _start_streamlit() -> subprocess.Popen:
    env = os.environ.copy()
    env["LOCREACH_HEARTBEAT_PORT"] = str(HEARTBEAT_PORT)
    return subprocess.Popen(
        [
            _venv_python(),
            "-m",
            "streamlit",
            "run",
            "Domain_Discovery.py",
            "--server.headless",
            "true",
            "--server.port",
            str(STREAMLIT_PORT),
            "--server.fileWatcherType",
            "none",
        ],
        cwd=BASE_DIR,
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def main() -> None:
    _setup_logging()
    _log(
        f"starting LocReach "
        f"(streamlit={STREAMLIT_PORT} heartbeat={HEARTBEAT_PORT} "
        f"shutdown_timeout={SHUTDOWN_TIMEOUT}s)"
    )
    _wait_for_free_port(STREAMLIT_PORT)
    _wait_for_free_port(HEARTBEAT_PORT)

    threading.Thread(target=_heartbeat_server, daemon=True).start()
    threading.Thread(target=_watchdog, daemon=True).start()
    threading.Thread(target=_open_browser_when_ready, daemon=True).start()

    global _streamlit_proc
    _streamlit_proc = _start_streamlit()
    _log(f"Streamlit started pid={_streamlit_proc.pid}")
    code = _streamlit_proc.wait()
    _log(f"Streamlit exited on its own code={code}")
    os._exit(code or 0)


if __name__ == "__main__":
    main()
