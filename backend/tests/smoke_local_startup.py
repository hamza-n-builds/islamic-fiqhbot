"""Real local startup/HTTP smoke check; external network and browser disabled.

Run with backend/venv's Python. Existing local model/NLTK resources are needed.
No /ask generation, Gemini calls, WhatsApp messages or Mongo writes are made.
"""
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
EVIDENCE = PROJECT / "replica" / "evidence"
OFFLINE_SERVER = """
import importlib.util,socket,sys
from pathlib import Path
connect=socket.socket.connect
def local_connect(self,address):
    if not isinstance(address,tuple) or address[0] not in ('127.0.0.1','::1','localhost'):
        raise OSError('External networking disabled for startup smoke check')
    return connect(self,address)
socket.socket.connect=local_connect
getaddrinfo=socket.getaddrinfo
def local_dns(host,*args,**kwargs):
    if host not in ('127.0.0.1','::1','localhost',None):
        raise OSError('External DNS disabled for startup smoke check')
    return getaddrinfo(host,*args,**kwargs)
socket.getaddrinfo=local_dns
script,cache=sys.argv[1:3]
sys.argv=[script,'--no-browser']
spec=importlib.util.spec_from_file_location('fiqhbot_smoke_server',script)
server=importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
server.CACHE_DIR=Path(cache)
server.STATE_PATH=server.CACHE_DIR/'local_server.json'
raise SystemExit(server.main())
"""


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (BACKEND / ".cache").mkdir(exist_ok=True)
    runtime = tempfile.TemporaryDirectory(prefix="startup-smoke-", dir=BACKEND / ".cache")
    command = [sys.executable, "-B", "-u", "-c", OFFLINE_SERVER, str(BACKEND / "start_local.py"), runtime.name]
    env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONIOENCODING="utf-8")
    started = time.monotonic()
    report = {"checks": [], "external_network": "blocked in server processes",
              "provider_generation_tested": False, "browser_rendering_tested": False}
    output = queue.Queue()
    process = subprocess.Popen(command, cwd=BACKEND, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
    lines = []
    url = None

    def collect():
        for line in process.stdout:
            lines.append(line)
            output.put(line)

    reader = threading.Thread(target=collect, daemon=True)
    reader.start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        while time.monotonic() - started < 180:
            try:
                line = output.get(timeout=0.5)
            except queue.Empty:
                if process.poll() is not None:
                    raise RuntimeError("Server exited before readiness; see local-startup-server.log")
                continue
            match = re.search(r"^FIQHBOT is ready at (http://127\.0\.0\.1:\d+/)", line)
            if match:
                url = match.group(1)
                break
        if not url:
            raise RuntimeError("Server did not become ready within 180 seconds")
        report["startup_seconds"] = round(time.monotonic() - started, 2)
        with opener.open(url + "health", timeout=5) as response:
            health = json.load(response)
            assert response.status == 200 and health["engine_ready"] is True, health
        report["checks"].append("Actual datasets/model warm-up and /health readiness")
        for name in ("index.html", "script.js", "style.css", "modern.css", "resize.js"):
            route = "" if name == "index.html" else name
            with opener.open(url + route, timeout=5) as response:
                body = response.read()
                assert response.status == 200
                assert hashlib.sha256(body).digest() == hashlib.sha256((PROJECT / "frontend" / name).read_bytes()).digest()
        report["checks"].append("HTML and four frontend assets served byte-for-byte")
        with opener.open(url + "config.js", timeout=5) as response:
            config = json.loads(response.read().decode().removeprefix("const CONFIG = ").removesuffix(";"))
            assert config["API_KEY"] == "" and config["BACKEND_URL"] == url.rstrip("/")
            assert response.headers["Cache-Control"] == "no-store"
        report["checks"].append("Same-origin dynamic config with blank browser API key")
        request = urllib.request.Request(url + "ask", data=b"{}", headers={"Content-Type": "application/json"})
        try:
            opener.open(request, timeout=5)
            raise AssertionError("Empty question was accepted")
        except urllib.error.HTTPError as error:
            assert error.code == 400 and json.load(error)["ok"] is False
        report["checks"].append("Invalid question rejected before generation")
        history_request = urllib.request.Request(
            url + "ask", data=json.dumps({"question": "explain in roman urdu",
                                          "prev_answer": "Untrusted fixture [Quran 1:1].",
                                          "prev_answer_receipt": "invalid-proof"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with opener.open(history_request, timeout=5) as response:
            rejected = json.load(response)
            assert response.status == 200 and rejected["mode"] == "low_confidence"
            assert rejected["citation_validation"]["reason"] == "unverified_history"
            assert "Untrusted fixture" not in rejected["answer"] and "answer_receipt" not in rejected
        report["checks"].append("Real API rejects unverified history without an external provider call")
        for question, mode in (("Hello", "greeting"), ("what can I ask", "capability"), ("help", "low_confidence")):
            status_request = urllib.request.Request(
                url + "ask", data=json.dumps({"question": question}).encode(),
                headers={"Content-Type": "application/json"})
            with opener.open(status_request, timeout=5) as response:
                result = json.load(response)
                assert response.status == 200 and result["mode"] == mode
                assert all(result.get(field) is None for field in
                           ("confidence", "confidence_percent", "confidence_label", "consensus"))
                assert "scholarly_review" not in result and "answer_receipt" not in result
        report["checks"].append("Real API greetings/capabilities/clarifications have no accuracy or consensus claims")
        for collection, number in (("Sahih Bukhari", "1395"), ("Sahih Muslim", "11a")):
            query = urllib.parse.urlencode({"source": collection, "number": number})
            with opener.open(url + "hadith-text?" + query, timeout=5) as response:
                record = json.load(response)
                assert record["found"] and record["text_en"].strip()
                assert record["source_identity"]["status"] == "primary_arabic_text_matched"
                assert record["reference_url"].startswith("https://sunnah.com/")
        report["checks"].append("Real API serves canonical Bukhari 1395 and Muslim 11a with pinned source provenance")
        with opener.open(url + "hadith-text?source=Sahih%20Muslim&number=11", timeout=5) as response:
            assert json.load(response)["found"] is False
        report["checks"].append("Ambiguous legacy Muslim 11 cannot resolve through the canonical API")
        reused = subprocess.run(command, cwd=BACKEND, env=env, capture_output=True,
                                encoding="utf-8", errors="replace", timeout=45)
        assert reused.returncode == 0 and "Opening the existing FIQHBOT at " + url in reused.stdout, reused.stdout
        report["checks"].append("Second launch reuses the ready instance without a browser")
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
    finally:
        if process.poll() is None:
            process.terminate()  # Only this smoke check's server process.
        process.wait(timeout=10)
        reader.join(timeout=5)
        process.stdout.close()
        state = Path(runtime.name) / "local_server.json"
        if url and state.is_file() and json.loads(state.read_text(encoding="utf-8")).get("url") == url:
            state.unlink()
        runtime.cleanup()
        (EVIDENCE / "local-startup-server.log").write_text("".join(lines), encoding="utf-8")
        (EVIDENCE / "local-startup.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
