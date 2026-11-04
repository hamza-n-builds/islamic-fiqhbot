"""API boundary regressions; all AI, logging, and WhatsApp calls are mocked.

Run: python -m unittest discover -s tests -v (from backend).
No credentials, model downloads, or external messages are used.
"""
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


def load_api():
    rag = types.ModuleType("rag_engine")
    rag._READY = True
    rag.answer_question = Mock(return_value={"ok": True, "answer": "Test answer"})
    database = types.ModuleType("db")
    database.log_query_async = Mock()
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = Mock()
    spec = importlib.util.spec_from_file_location("fiqhbot_test_api", Path(__file__).parents[1] / "app.py")
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, "path", [str(Path(__file__).parents[1]), *sys.path]), patch.dict(sys.modules, {"rag_engine": rag, "db": database, "dotenv": dotenv}):
        spec.loader.exec_module(module)
    module.app.config["TESTING"] = True
    module.app.logger.disabled = True
    return module, rag, database


class ApiBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api, cls.rag, cls.database = load_api()

    def setUp(self):
        self.client = self.api.app.test_client()
        self.rag.answer_question.reset_mock(side_effect=True)
        self.database.log_query_async.reset_mock()

    def test_invalid_json_shapes_are_rejected_before_generation(self):
        for body in ([], [1], "question", 5, None, {"question": 5}, {"question": {}},
                     {"question": "hello", "madhab": []}, {"question": "hello", "prev_answer": 7},
                     {"question": "hello", "prev_answer_receipt": []}):
            with self.subTest(body=body):
                response = self.client.post("/ask", data=json.dumps(body), content_type="application/json")
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json["ok"])
        self.rag.answer_question.assert_not_called()

    def test_empty_and_oversized_fields_do_not_reach_model(self):
        for body in ({}, {"question": "  "}, {"question": "a" * 4001},
                     {"question": "hello", "prev_answer": "a" * 20001},
                     {"question": "hello", "prev_answer_receipt": "a" * 8193}):
            with self.subTest(keys=list(body)):
                self.assertEqual(self.client.post("/ask", json=body).status_code, 400)
        self.rag.answer_question.assert_not_called()

    def test_aliases_and_school_selection_still_work(self):
        response = self.client.post("/ask", json={"text": " A question ", "madhhab": "Hanafi"})
        self.assertEqual(response.status_code, 200)
        self.rag.answer_question.assert_called_once_with("A question", "Hanafi", prev_answer=None, prev_answer_receipt=None)
        self.database.log_query_async.assert_called_once()
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_bad_school_falls_back_to_general(self):
        self.client.post("/ask", json={"question": "hello", "madhab": "unsupported"})
        self.rag.answer_question.assert_called_once_with("hello", None, prev_answer=None, prev_answer_receipt=None)

    def test_translation_proof_is_forwarded_without_becoming_a_credential(self):
        response = self.client.post("/ask", json={"question": "explain in roman urdu", "prev_answer": "earlier text", "prev_answer_receipt": "opaque-proof"})
        self.assertEqual(response.status_code, 200)
        self.rag.answer_question.assert_called_once_with("explain in roman urdu", None,
                                                       prev_answer="earlier text", prev_answer_receipt="opaque-proof")

    def test_provider_errors_do_not_disclose_internal_values(self):
        self.rag.answer_question.side_effect = RuntimeError("private-provider-value")
        response = self.client.post("/ask", json={"question": "hello"})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(b"private-provider-value", response.data)

    def test_large_bodies_get_json_413(self):
        response = self.client.post("/ask", data=b" " * (1024 * 1024 + 1), content_type="application/json")
        self.assertEqual(response.status_code, 413)
        self.assertFalse(response.json["ok"])

    def test_unlisted_origin_does_not_get_cors_access(self):
        response = self.client.post("/ask", json={"question": "hello"}, headers={"Origin": "https://unlisted.example"})
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_webhook_requires_configured_secret_and_valid_signature(self):
        with patch.object(self.api, "WA_APP_SECRET", ""):
            self.assertEqual(self.client.post("/whatsapp", json={}).status_code, 503)
        with patch.object(self.api, "WA_APP_SECRET", "test-secret"):
            for signature in ("", "sha256=bad", "sha256=\u00e9"):
                with self.subTest(signature=signature):
                    response = self.client.post("/whatsapp", json={}, headers={"X-Hub-Signature-256": signature})
                    self.assertEqual(response.status_code, 403)
        self.rag.answer_question.assert_not_called()

    def test_signed_webhook_reaches_mocked_channel(self):
        payload = {"entry": [{"changes": [{"value": {"messages": [{
            "from": "synthetic-recipient", "type": "text", "text": {"body": "Test question"}
        }]}}]}]}
        body = json.dumps(payload, ensure_ascii=True).encode()
        signature = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        with patch.object(self.api, "WA_APP_SECRET", "test-secret"), patch.object(self.api, "wa_send_text") as send:
            response = self.client.post("/whatsapp", data=body, content_type="application/json",
                                        headers={"X-Hub-Signature-256": signature})
            self.assertEqual(response.status_code, 200)
            self.rag.answer_question.assert_called_once_with("Test question", None)
            send.assert_called_once()

    def test_handshake_requires_explicit_token(self):
        with patch.object(self.api, "WA_VERIFY_TOKEN", ""):
            self.assertEqual(self.client.get("/whatsapp?hub.mode=subscribe&hub.verify_token=&hub.challenge=test").status_code, 403)
        with patch.object(self.api, "WA_VERIFY_TOKEN", "test-token"):
            response = self.client.get("/whatsapp?hub.mode=subscribe&hub.verify_token=test-token&hub.challenge=test")
            self.assertEqual(response.data, b"test")

    def test_speech_validation_and_cleanup_on_success_and_failure(self):
        for body in ([], {"text": 2}, {"text": "a" * 20001}):
            self.assertEqual(self.client.post("/speak", json=body).status_code, 400)
        for fail in (False, True):
            with self.subTest(fail=fail):
                paths = []
                voice = types.ModuleType("voice")
                voice.strip_citations = lambda text: text
                def synthesize(text, filename, lang):
                    path = Path(filename)
                    paths.append(path)
                    path.write_bytes(b"synthetic-mp3")
                    self.addCleanup(path.unlink, missing_ok=True)
                    if fail:
                        raise RuntimeError("private-speech-error")
                voice.synthesize = synthesize
                with patch.dict(sys.modules, {"voice": voice}):
                    response = self.client.post("/speak", json={"text": "hello"})
                    self.assertEqual(response.status_code, 500 if fail else 200)
                    if not fail:
                        self.assertEqual(response.data, b"synthetic-mp3")
                    self.assertNotIn(b"private-speech-error", response.data)
                    self.assertTrue(paths)
                    self.assertFalse(paths[0].exists())
                    self.assertFalse(paths[0].parent.exists())
                    response.close()


if __name__ == "__main__":
    unittest.main()
