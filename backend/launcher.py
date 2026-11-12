"""Entry point for the packaged desktop app: start the server, open the browser."""

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

APP = "MootCourtMemorialToolkit"


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP


def free_port(preferred: int = 8765) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("No free port available")


def main():
    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    os.environ.setdefault("MCMT_DATA_DIR", str(data_dir()))
    os.environ.setdefault("MCMT_STATIC_DIR", str(bundle / "web"))

    import uvicorn

    from app.main import app

    port = int(os.environ.get("MCMT_PORT") or free_port())
    url = f"http://127.0.0.1:{port}"
    print("Moot Court Memorial Toolkit", flush=True)
    print(f"  Running at {url}", flush=True)
    print(f"  Your projects and uploads are stored in {os.environ['MCMT_DATA_DIR']}", flush=True)
    print("  Keep this window open while you work. Close it to stop the app.\n", flush=True)
    if not os.environ.get("MCMT_NO_BROWSER"):
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
