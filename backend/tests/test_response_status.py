"""Response transparency regressions; synthetic records, no provider/network calls."""
import math
import hashlib
import hmac
import json
import unittest
from unittest.mock import patch

import test_citation_integrity as fixtures
from test_api_boundary import load_api

rag = fixtures.rag


class ResponseStatusTests(unittest.TestCase):
    # Reuse source/provider fixtures; the original regression suite runs separately.
    setUp = fixtures.CitationPathTests.setUp
    assertBlocked = fixtures.CitationPathTests.assertBlocked
    translated = fixtures.CitationPathTests.translated
    api_client = fixtures.CitationPathTests.api_client

    def assertTransparent(self, result):
        for field in ("confidence", "confidence_percent", "confidence_label", "confidence_reason", "consensus"):
            self.assertIsNone(result.get(field), field)
        self.assertEqual(result["citation_validation"], {
            "status": "passed", "scope": "provided_reference_membership"})
        self.assertEqual(result["scholarly_review"], {
            "status": "not_completed", "scope": "answer_and_ruling_support"})
        for topic in result["sources"]["fiqh"]:
            self.assertIsNone(topic.get("consensus"))

    def test_curated_answer_cannot_turn_pending_consensus_into_certification(self):
        self.topic["consensus"] = True
        result = rag.answer_question("What is the fixture ruling?")
        self.assertTransparent(result)
        prompt = self.provider.call_args.args[0]
        self.assertNotIn("Scholarly Consensus: Yes", prompt)
        self.assertNotIn("Certainty:", prompt)
        self.assertIn("not been independently reviewed", prompt)
        self.assertIn("Do not claim consensus", prompt)

    def test_false_or_missing_dataset_flag_is_not_proof_of_scholarly_disagreement(self):
        for flag in (False, None):
            with self.subTest(flag=flag):
                self.topic["consensus"] = flag
                result = rag.answer_question("What is the fixture ruling?")
                self.assertTransparent(result)
                self.assertNotIn("No - scholars differ", self.provider.call_args.args[0])

    def test_general_answer_has_no_fixed_accuracy_score(self):
        self.provider.return_value = "Fixture answer [Quran 1:1]."
        result = rag._general_result("Describe the fixture topic", topic_id="fixture", topic_score=0.95)
        self.assertTransparent(result)
        self.assertIn("Do not claim consensus", self.provider.call_args.args[0])

    def test_translation_retains_transparency_and_provenance(self):
        self.topic["rulings"]["hanafi"]["certainty"] = "Very High"
        first = rag.answer_question("What is the fixture ruling?")
        result = self.translated(first, "Fixture tarjuma [Fixture topic] [Quran 1:1].")
        self.assertTransparent(result)
        self.assertTrue(result["answer_receipt"])
        self.assertNotIn('"certainty"', self.provider.call_args.args[0])

    def test_unreviewed_or_unstructured_review_flag_does_not_become_approval(self):
        for review in (None, "pending", "approved", {"status": "approved"}):
            with self.subTest(review=review):
                self.topic["scholar_review"] = review
                self.assertTransparent(rag.answer_question("What is the fixture ruling?"))

    def test_weak_general_match_is_withheld_before_provider_even_with_dataset_consensus(self):
        self.topic["consensus"] = True
        for score in (0.0, 0.34, 0.5, 0.64, math.nan, math.inf, -1.0, 1.1):
            with self.subTest(score=score):
                self.provider.reset_mock()
                result = rag._general_result("Describe the fixture topic", topic_id="fixture", topic_score=score)
                self.provider.assert_not_called()
                self.assertBlocked(result)
                self.assertIsNone(result.get("confidence_percent"))

    def test_consensus_flag_cannot_bypass_existing_strict_retrieval_policy(self):
        self.topic["consensus"] = True
        with patch.object(rag, "LOW_CONFIDENCE_PCT", 85):
            result = rag.answer_question("What is the fixture ruling?")
        self.provider.assert_not_called()
        self.assertBlocked(result)
        self.assertIsNone(result.get("confidence_percent"))

    def test_weak_primary_match_cannot_fall_through_to_general_generation(self):
        for score in (0.0, 0.5, 0.64, math.nan, math.inf):
            with self.subTest(score=score), patch.object(rag, "classify_topic", return_value=[("fixture", score)]):
                self.provider.reset_mock()
                with patch.object(rag, "_general_result") as general, patch.object(rag, "retrieve_fiqh_ruling") as retrieval:
                    result = rag.answer_question("What is the fixture ruling?")
                self.assertBlocked(result)
                self.provider.assert_not_called()
                retrieval.assert_not_called()
                general.assert_not_called()

    def test_old_signed_consensus_claim_is_not_forwarded_to_translation_provider(self):
        fiqh = [rag._fiqh_entry_by_id("fixture", score=0.95)]
        tags = {"[Fixture topic]", "[Quran 1:1]"}
        first = rag._with_receipt({"answer": "All major schools agree [Fixture topic] [Quran 1:1]."},
                                  tags, fiqh, [], [self.verse])
        result = self.translated(first, "Fixture tarjuma [Fixture topic] [Quran 1:1].")
        self.provider.assert_not_called()
        self.assertBlocked(result)

    def test_individual_school_position_is_still_allowed(self):
        self.provider.return_value = "The Hanafi position in these dataset notes is the fixture ruling [Fixture topic]."
        result = rag.answer_question("What is the fixture ruling?")
        self.assertTransparent(result)
        self.assertEqual(result["answer"], self.provider.return_value)

    def test_generated_unreviewed_agreement_claim_is_withheld_in_all_generation_paths(self):
        first = rag.answer_question("What is the fixture ruling?")
        for claim in ("All major schools agree", "Scholarly consensus", "Ijma", "Tamam masalik muttafiq hain", "اجماع", "إجماع"):
            with self.subTest(claim=claim):
                output = claim + " [Fixture topic] [Quran 1:1]."
                self.provider.return_value = output
                self.assertBlocked(rag.answer_question("What is the fixture ruling?"))
                self.provider.return_value = claim + " [Quran 1:1]."
                self.assertBlocked(rag._general_result("Describe the fixture topic", topic_id="fixture", topic_score=0.95))
                self.assertBlocked(self.translated(first, output))

    def test_greetings_referrals_and_rejections_do_not_claim_accuracy_or_disagreement(self):
        for gate in ("_is_greeting", "_is_capability_question", "_is_gibberish", "_is_vague_question", "_is_sensitive_question"):
            with self.subTest(gate=gate), patch.object(rag, gate, return_value=True):
                result = rag.answer_question("Fixture question")
                self.assertIsNone(result.get("confidence_percent"))
                self.assertIsNone(result.get("confidence_label"))
                self.assertIsNone(result.get("consensus"))
                self.assertNotIn("scholarly_review", result)

    def test_api_returns_honest_status_contract(self):
        response = self.api_client().post("/ask", json={"question": "What is the fixture ruling?"})
        self.assertEqual(response.status_code, 200)
        self.assertTransparent(response.json)


class WhatsAppStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api, cls.channel_rag, _ = load_api()

    def test_legacy_values_and_greetings_do_not_leak_percentage_or_consensus(self):
        for mode in ("greeting", "capability", "low_confidence", "fiqh"):
            result = {"ok": True, "mode": mode, "answer": "Fixture answer", "confidence_percent": 99,
                      "confidence_label": "Very High", "consensus": True}
            formatted = self.api._format_for_whatsapp(result)
            self.assertEqual(formatted, "Fixture answer")

    def test_accepted_citations_have_explicitly_limited_checks_and_incomplete_review(self):
        formatted = self.api._format_for_whatsapp({
            "ok": True, "mode": "fiqh", "answer": "Fixture answer",
            "citation_validation": {"status": "passed", "scope": "provided_reference_membership"},
            "scholarly_review": {"status": "not_completed", "scope": "answer_and_ruling_support"},
        })
        self.assertIn("References matched", formatted)
        self.assertIn("Scholarly review not completed", formatted)
        self.assertIn("does not verify the answer's accuracy", formatted)
        self.assertNotIn("Confidence:", formatted)
        self.assertNotIn("agree", formatted)

    def test_signed_webhook_delivers_the_same_scoped_status_without_live_send(self):
        result = {"ok": True, "mode": "fiqh", "answer": "Fixture answer",
                  "citation_validation": {"status": "passed", "scope": "provided_reference_membership"},
                  "scholarly_review": {"status": "not_completed", "scope": "answer_and_ruling_support"}}
        self.channel_rag.answer_question.return_value = result
        payload = {"entry": [{"changes": [{"value": {"messages": [{
            "from": "synthetic-recipient", "type": "text", "text": {"body": "Fixture question"}
        }]}}]}]}
        body = json.dumps(payload).encode()
        signature = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        with patch.object(self.api, "WA_APP_SECRET", "test-secret"), patch.object(self.api, "wa_send_text") as send:
            response = self.api.app.test_client().post("/whatsapp", data=body, content_type="application/json",
                                                       headers={"X-Hub-Signature-256": signature})
        self.assertEqual(response.status_code, 200)
        send.assert_called_once_with("synthetic-recipient", self.api._format_for_whatsapp(result))
        self.assertIn("Scholarly review not completed", send.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
