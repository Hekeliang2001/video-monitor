from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser

import uvicorn


def can_bind(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind((host, port))
            return True
        except OSError:
            return False


def choose_port(host: str, preferred_port: int) -> int:
    candidates = [preferred_port]
    candidates.extend(range(preferred_port + 1, preferred_port + 50))
    candidates.extend(range(18000, 18100))

    seen: set[int] = set()
    for port in candidates:
        if port in seen:
            continue
        seen.add(port)
        if can_bind(host, port):
            return port

    raise RuntimeError("No available local port was found.")


def open_browser_later(url: str) -> None:
    def open_browser() -> None:
        time.sleep(1.2)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()


def run_control_panel() -> None:
    import web_app

    host = os.getenv("VIDEO_MONITOR_HOST", "127.0.0.1")
    preferred_port = int(os.getenv("VIDEO_MONITOR_PORT", "8000"))
    port = choose_port(host, preferred_port)
    browser_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{browser_host}:{port}/"

    if port != preferred_port:
        print(f"Port {preferred_port} is unavailable; using port {port}.")
    print(f"Video Monitor Console: {url}")
    print("Keep this window open while using the control panel.")
    open_browser_later(url)
    uvicorn.run(web_app.app, host=host, port=port, loop="asyncio", http="h11", use_colors=False)


def run_worker() -> None:
    import main

    sys.argv = [sys.argv[0], *sys.argv[2:]]
    main.main()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        run_worker()
    else:
        run_control_panel()
