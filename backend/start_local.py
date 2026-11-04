"""Start FIQHBOT for one person on this computer and open its web interface."""

import os
import json
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from werkzeug.serving import make_server

BACKEND_DIR = Path(__file__).resolve().parent
os.chdir(BACKEND_DIR)

import app as fiqh_app  # loads backend/.env before importing the engine
import rag_engine

CACHE_DIR = BACKEND_DIR / ".cache"
STATE_PATH = CACHE_DIR / "local_server.json"


def _lock_instance():
    CACHE_DIR.mkdir(exist_ok=True)
    lock_file = open(CACHE_DIR / "local_server.lock", "a+b")
    lock_file.seek(0, os.SEEK_END)
    if lock_file.tell() == 0:
        lock_file.write(b"\0")
        lock_file.flush()
    lock_file.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_file.close()
        return None
    return lock_file


def _reuse_running_instance():
    print("FIQHBOT is already starting or running. Waiting for its page...")
    for _ in range(180):
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            url = state["url"]
            with urllib.request.urlopen(url + "health", timeout=2) as response:
                if json.load(response).get("engine_ready"):
                    print(f"Opening the existing FIQHBOT at {url}")
                    if "--no-browser" not in sys.argv:
                        webbrowser.open(url)
                    return 0
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(1)
    print("The existing FIQHBOT did not become ready. Close its window and try again.")
    return 1


def main():
    lock_file = _lock_instance()
    if lock_file is None:
        return _reuse_running_instance()
    try:
        STATE_PATH.unlink(missing_ok=True)
        return _start_new_instance()
    finally:
        STATE_PATH.unlink(missing_ok=True)
        lock_file.close()


def _start_new_instance():
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        print("Missing Gemini API key. Add GEMINI_API_KEY to backend/.env, then start again.")
        return 1

    print("Preparing FIQHBOT's local knowledge base. The browser will open when it is ready...")
    fiqh_app.start_warmup()
    while not rag_engine._READY and fiqh_app._warm_thread and fiqh_app._warm_thread.is_alive():
        time.sleep(0.25)
    if not rag_engine._READY:
        print("FIQHBOT could not load its knowledge base. Check the error above.")
        return 1

    server = make_server("127.0.0.1", 0, fiqh_app.app, threaded=True)
    url = f"http://127.0.0.1:{server.server_port}/"
    STATE_PATH.write_text(json.dumps({"url": url}), encoding="utf-8")
    print(f"FIQHBOT is ready at {url}")
    print("Keep this window open while using FIQHBOT. Press Ctrl+C to stop it.")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping FIQHBOT...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
