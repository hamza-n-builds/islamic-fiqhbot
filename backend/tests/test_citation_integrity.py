"""Real response-path tests with synthetic sources and a mocked provider.

These verify citation/provenance boundaries, not Islamic content correctness.
"""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import types
import unittest
from unittest.mock import Mock, patch

BACKEND = Path(__file__).resolve().parents[1]
with patch.dict(os.environ, {"GEMINI_API_KEY": "", "FIQHBOT_RESPONSE_SECRET": "test-only-receipt-secret-32-characters"}), patch.object(sys, "path", [str(BACKEND), *sys.path]):
    spec = importlib.util.spec_from_file_location("fiqhbot_citation_test_rag", BACKEND / "rag_engine.py")
    rag = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rag)


class CitationPathTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("No test network")))
        self.topic = {
            "topic_id": "fixture", "topic_name": "Fixture topic", "description": "Synthetic test source",
            "consensus": False, "scholar_review": "pending",
            "rulings": {"hanafi": {"ruling": "Fixture ruling", "explanation": "Fixture explanation"}},
            "references": {"quran": [{"chapter": 1, "ayah": 1}], "hadith": []},
        }
        self.verse = {"chapter": 1, "ayah": 1, "surah_name_en": "Fixture surah", "english": "Synthetic verse text", "arabic": "", "urdu": "", "score": 1.0}
        self.enterContext(patch.object(rag, "_READY", True))
        self.enterContext(patch.object(rag, "fiqh_topics", [self.topic]))
        self.enterContext(patch.object(rag, "quran_lookup", {(1, 1): self.verse}))
        self.enterContext(patch.object(rag, "hadith_lookup", {}))
        self.enterContext(patch.object(rag, "LOW_CONFIDENCE_PCT", 50))
        for name in ("_is_greeting", "_is_capability_question", "_is_meta_instruction", "_is_gibberish", "_is_vague_question", "_is_sensitive_question", "_force_general"):
            self.enterContext(patch.object(rag, name, return_value=False))
        self.enterContext(patch.object(rag, "_detect_language", return_value="English"))
        self.enterContext(patch.object(rag, "classify_topic", return_value=[("fixture", 0.95)]))
        self.enterContext(patch.object(rag, "retrieve_fiqh_ruling", side_effect=lambda *a, **kw: [rag._fiqh_entry_by_id("fixture", score=0.95)]))
        self.enterContext(patch.object(rag, "retrieve_quran", return_value=[self.verse]))
        self.provider = self.enterContext(patch.object(rag, "gemini_generate", return_value="Fixture answer [Fixture topic] [Quran 1:1]."))

    def assertBlocked(self, result):
        self.assertEqual(result["mode"], "low_confidence")
        self.assertNotIn("Fixture answer", result["answer"])
        self.assertEqual(result["sources"], {"fiqh": [], "quran": [], "hadith": []})

    def test_curated_rejects_unprovided_quran_reference(self):
        self.provider.return_value = "Fixture answer [Quran 999:999]."
        self.assertBlocked(rag.answer_question("What is the fixture ruling?"))

    def test_curated_rejects_unprovided_topic_reference(self):
        self.provider.return_value = "Fixture answer [Imaginary topic]."
        self.assertBlocked(rag.answer_question("What is the fixture ruling?"))

    def test_general_rejects_whole_answer_instead_of_only_stripping_invalid_tag(self):
        self.provider.return_value = "Fixture answer [Quran 999:999]."
        self.assertBlocked(rag._general_result("Describe the fixture topic", topic_id="fixture", topic_score=0.95))

    def test_general_without_sources_never_calls_provider(self):
        result = rag._general_result("Describe the fixture topic")
        self.provider.assert_not_called()
        self.assertBlocked(result)

    def test_context_refusal_does_not_trigger_general_generation(self):
        self.provider.return_value = "This requires consultation with a qualified scholar."
        with patch.object(rag, "_general_result") as general:
            result = rag.answer_question("What is the fixture ruling?")
            general.assert_not_called()
        self.assertBlocked(result)

    def test_translation_without_server_proof_does_not_call_provider(self):
        with patch.object(rag, "_is_meta_instruction", return_value=True):
            result = rag.answer_question("explain in roman urdu", prev_answer="Fixture answer [Quran 1:1].")
        self.provider.assert_not_called()
        self.assertBlocked(result)

    def test_valid_supplied_citations_still_work(self):
        result = rag.answer_question("What is the fixture ruling?")
        self.assertEqual(result["mode"], "fiqh")
        self.assertIn("[Quran 1:1]", result["answer"])
        self.assertEqual(result["sources"]["quran"][0]["ref"], "1:1")

    def test_unused_source_metadata_is_not_displayed_as_evidence(self):
        self.provider.return_value = "Fixture answer [Fixture topic]."
        result = rag.answer_question("What is the fixture ruling?")
        self.assertEqual(result["sources"]["quran"], [])
        self.assertEqual(result["sources"]["fiqh"][0]["scholar_review"], "pending")

    def test_record_exists_but_was_not_supplied_still_cannot_be_cited(self):
        rag.quran_lookup[(2, 2)] = {**self.verse, "chapter": 2, "ayah": 2}
        self.provider.return_value = "Fixture answer [Quran 2:2]."
        self.assertBlocked(rag.answer_question("What is the fixture ruling?"))

    def test_blank_source_text_is_excluded_from_prompt_and_citation_allowlist(self):
        for value in ("   ", None, []):
            with self.subTest(value=value):
                self.verse["english"] = value
                result = rag._general_result("Describe the fixture topic", topic_id="fixture", topic_score=0.95)
                self.provider.assert_not_called()
                self.assertBlocked(result)

    def test_empty_hadith_text_is_not_context_even_with_an_id_and_arabic(self):
        self.topic["references"] = {"hadith": [{"source": "Sahih Muslim", "hadith_no": 11}]}
        rag.hadith_lookup[("Sahih Muslim", "11")] = {"source": "Sahih Muslim", "hadith_no": 11, "text_en": "", "text_ar": "Synthetic untranslated text"}
        self.provider.return_value = "Fixture answer [Sahih Muslim #11]."
        self.assertBlocked(rag.answer_question("What is the fixture ruling?"))
        self.assertNotIn("[Sahih Muslim #11]", self.provider.call_args.args[0])

    def test_missing_reference_records_do_not_become_context(self):
        rag.quran_lookup.clear()
        result = rag._general_result("Describe the fixture topic", topic_id="fixture", topic_score=0.95)
        self.provider.assert_not_called()
        self.assertBlocked(result)

    def test_source_on_grade_review_hold_cannot_enter_generation_context(self):
        self.topic["references"] = {"hadith": [{"source": "Sahih Muslim", "hadith_no": "11a"}]}
        rag.hadith_lookup[("Sahih Muslim", "11a")] = {"source": "Sahih Muslim", "hadith_no": "11a",
                                                   "text_en": "Fixture source on hold", "generation_eligible": False}
        self.assertBlocked(rag._general_result("Describe the fixture topic", topic_id="fixture", topic_score=0.95))
        self.provider.assert_not_called()

    def test_no_eligible_hadith_search_returns_no_candidates(self):
        with patch.object(rag, "hadith_data", []), patch.object(rag, "bm25_hadith", None):
            self.assertEqual(rag.retrieve_hadith("Fixture question"), [])

    def test_general_valid_citation_returns_only_used_source_and_receipt(self):
        self.provider.return_value = "Fixture answer [Quran 1:1]."
        result = rag._general_result("Describe the fixture topic", topic_id="fixture", topic_score=0.95)
        self.assertEqual(result["mode"], "general")
        self.assertTrue(result["answer_receipt"])
        self.assertIsNone(result["consensus"])

    def translated(self, first, text):
        self.provider.reset_mock()
        self.provider.return_value = text
        with patch.object(rag, "_is_meta_instruction", return_value=True):
            return rag.answer_question("explain in roman urdu", prev_answer=first["answer"],
                                       prev_answer_receipt=first["answer_receipt"])

    def test_valid_translation_preserves_sources_and_refreshes_proof(self):
        first = rag.answer_question("What is the fixture ruling?")
        result = self.translated(first, "Fixture tarjuma [Fixture topic] [Quran 1:1].")
        self.assertEqual(result["mode"], "reexpress")
        self.assertEqual(result["sources"]["quran"][0]["ref"], "1:1")
        self.assertTrue(result["answer_receipt"])

    def test_translation_cannot_introduce_or_drop_a_citation(self):
        first = rag.answer_question("What is the fixture ruling?")
        for output in ("Fixture answer [Quran 999:999].", "Fixture answer [Fixture topic]."):
            with self.subTest(output=output):
                self.assertBlocked(self.translated(first, output))

    def test_modified_prior_answer_is_rejected_before_generation(self):
        first = rag.answer_question("What is the fixture ruling?")
        first["answer"] += " Extra invented claim."
        result = self.translated(first, "Fixture answer [Fixture topic] [Quran 1:1].")
        self.provider.assert_not_called()
        self.assertBlocked(result)

    def test_source_changes_invalidate_prior_answer_receipt(self):
        first = rag.answer_question("What is the fixture ruling?")
        self.verse["english"] = "Updated synthetic source text"
        result = self.translated(first, "Fixture answer [Fixture topic] [Quran 1:1].")
        self.provider.assert_not_called()
        self.assertBlocked(result)

    def test_source_removal_invalidates_prior_answer_receipt(self):
        first = rag.answer_question("What is the fixture ruling?")
        rag.quran_lookup.clear()
        result = self.translated(first, "Fixture answer [Fixture topic] [Quran 1:1].")
        self.provider.assert_not_called()
        self.assertBlocked(result)

    def api_client(self):
        database = types.ModuleType("db")
        database.log_query_async = Mock()
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = Mock()
        spec = importlib.util.spec_from_file_location("fiqhbot_citation_flow_api", BACKEND / "app.py")
        api = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"rag_engine": rag, "db": database, "dotenv": dotenv}):
            spec.loader.exec_module(api)
        api.app.config["TESTING"] = True
        return api.app.test_client()

    def test_real_api_route_withholds_invalid_generated_reply(self):
        self.provider.return_value = "Fixture answer [Quran 999:999]."
        response = self.api_client().post("/ask", json={"question": "What is the fixture ruling?"})
        self.assertEqual(response.status_code, 200)
        self.assertBlocked(response.json)
        self.assertNotIn("answer_receipt", response.json)

    def test_real_api_route_round_trips_server_proof_into_translation(self):
        client = self.api_client()
        first = client.post("/ask", json={"question": "What is the fixture ruling?"}).json
        self.provider.return_value = "Fixture tarjuma [Fixture topic] [Quran 1:1]."
        with patch.object(rag, "_is_meta_instruction", return_value=True):
            response = client.post("/ask", json={"question": "explain in roman urdu", "prev_answer": first["answer"], "prev_answer_receipt": first["answer_receipt"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["mode"], "reexpress")
        self.assertEqual(response.json["sources"]["quran"][0]["ref"], "1:1")
        self.assertNotIn("FIQHBOT_RESPONSE_SECRET", json.dumps(response.json))

    def test_real_api_route_rejects_edited_history_before_provider_call(self):
        client = self.api_client()
        first = client.post("/ask", json={"question": "What is the fixture ruling?"}).json
        self.provider.reset_mock()
        with patch.object(rag, "_is_meta_instruction", return_value=True):
            response = client.post("/ask", json={"question": "explain in roman urdu", "prev_answer": first["answer"] + " Added claim.", "prev_answer_receipt": first["answer_receipt"]})
        self.assertEqual(response.status_code, 200)
        self.provider.assert_not_called()
        self.assertBlocked(response.json)


if __name__ == "__main__":
    unittest.main()
