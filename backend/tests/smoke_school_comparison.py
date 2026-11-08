"""Real loopback HTTP + real retrieval; synthetic organizer, never live Gemini.

The organizer checks school ownership and returns placeholders with actual supplied
reference identities. This verifies plumbing, not translation/religious accuracy.
"""
import json
import os
from pathlib import Path
import socket
import sys
import threading
import urllib.request
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def main():
    original_connect = socket.socket.connect
    original_dns = socket.getaddrinfo

    def local_connect(sock, address):
        if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1", "localhost"}:
            raise OSError("External networking disabled for comparison smoke")
        return original_connect(sock, address)

    def local_dns(host, *args, **kwargs):
        if host not in {"127.0.0.1", "::1", "localhost", None}:
            raise OSError("External DNS disabled for comparison smoke")
        return original_dns(host, *args, **kwargs)

    report = {"date": "2026-11-08", "checks": [], "external_network": "blocked",
              "retrieval": "real model/datasets", "organizer": "synthetic fixture; no live Gemini",
              "religious_or_translation_quality_tested": False, "browser_rendering_tested": False}
    with patch.dict(os.environ, {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "GEMINI_API_KEY": "",
                                "FIQHBOT_RESPONSE_SECRET": "synthetic-http-smoke-secret-32-characters"}), \
            patch("dotenv.load_dotenv", return_value=False), \
            patch.object(socket.socket, "connect", local_connect), patch.object(socket, "getaddrinfo", local_dns):
        import app as api
        from werkzeug.serving import make_server
        rag = api.rag_engine
        rag.init(verbose=False)
        topic_id = "five_daily_prayers"
        query = rag.topic_examples[topic_id][0]
        calls = []

        def organizer(prompt):
            payload = prompt.split("RETRIEVED SCHOOL CONTEXTS:\n", 1)[1].split("\n\nUSER QUESTION/INSTRUCTION:", 1)[0]
            scopes = json.loads(payload)
            calls.append(tuple(scopes))
            answers = {}
            for key, scope in scopes.items():
                note = scope["rulings"][0]
                assert set(note["notes"]) == {key}, "Another school's note leaked into this scope"
                assert note["notes"][key]["ruling"].strip()
                if "previous_answer" in scope:
                    answers[key] = scope["previous_answer"]
                else:
                    refs = scope["topic_level_shared_references"]["quran"]
                    tag = " " + refs[0]["tag"] if refs else ""
                    answers[key] = "Retrieved note for " + key + " " + note["topic_tag"] + tag + "."
            return json.dumps(answers)

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with patch.object(rag, "gemini_generate", side_effect=organizer), patch.object(api.db, "log_query_async"):
            server = make_server("127.0.0.1", 0, api.app)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/"

            def post(body):
                request = urllib.request.Request(url + "ask", json.dumps(body).encode(), {"Content-Type": "application/json"})
                with opener.open(request, timeout=30) as response:
                    assert response.status == 200
                    return json.load(response)

            try:
                first = post({"question": query})
                assert first["mode"] == "fiqh_comparison", first.get("mode")
                assert [s["school"] for s in first["answer_sections"]] == ["hanafi", "shafi", "maliki"]
                assert all(s["status"] == "available" for s in first["answer_sections"])
                assert len(calls) == 1 and first["answer_receipt"]
                report["checks"].append("Default /ask: real retrieval, three validated school sections, one organizer call")
                translated = post({"question": "explain in roman urdu", "prev_answer": first["answer"],
                                   "prev_answer_receipt": first["answer_receipt"]})
                assert translated["response_schema"] == "school_comparison_v1" and len(calls) == 2
                assert all(s["status"] == "available" for s in translated["answer_sections"])
                report["checks"].append("Signed rephrasing: school sections, references and new proof retained")
                rejected = post({"question": "explain in roman urdu", "prev_answer": first["answer"].replace("Retrieved note", "Edited note", 1),
                                 "prev_answer_receipt": first["answer_receipt"]})
                assert rejected["mode"] == "low_confidence" and len(calls) == 2
                report["checks"].append("Edited school answer rejected before organizer invocation")
                report.update(status="passed", topic_id=topic_id, organizer_calls=len(calls))
            except Exception as error:
                report.update(status="failed", error=type(error).__name__)
                raise
            finally:
                server.shutdown()
                thread.join(timeout=10)
                server.server_close()
                target = BACKEND.parent / "replica/evidence/school-comparison-http.json"
                target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
