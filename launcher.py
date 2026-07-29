from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

import uvicorn


def open_browser_later(url: str) -> None:
    def open_browser() -> None:
        time.sleep(1.2)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()


def run_control_panel() -> None:
    import web_app

    host = os.getenv("VIDEO_MONITOR_HOST", "127.0.0.1")
    port = int(os.getenv("VIDEO_MONITOR_PORT", "8000"))
    browser_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{browser_host}:{port}/"

    print(f"Video Monitor Console: {url}")
    print("Keep this window open while using the control panel.")
    open_browser_later(url)
    uvicorn.run(web_app.app, host=host, port=port, loop="asyncio", http="h11")


def run_worker() -> None:
    import main

    sys.argv = [sys.argv[0], *sys.argv[2:]]
    main.main()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        run_worker()
    else:
        run_control_panel()
