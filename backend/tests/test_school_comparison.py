"""Three-school RAG contract; synthetic school notes and a mocked organizer."""
import copy
import json
import unittest
from unittest.mock import patch

import test_citation_integrity as fixtures

rag = fixtures.rag
SCHOOLS = ("hanafi", "shafi", "maliki")


class SchoolComparisonTests(unittest.TestCase):
    api_client = fixtures.CitationPathTests.api_client

    def setUp(self):
        fixtures.CitationPathTests.setUp(self)
        self.topic["rulings"] = {key: {"ruling": key + " fixture position", "explanation": key + " fixture explanation"}
                                 for key in SCHOOLS}
        self.outputs = {key: key + " organized fixture [Fixture topic] [Quran 1:1]." for key in SCHOOLS}
        self.provider.side_effect = lambda prompt: json.dumps(self.outputs)

    def ask(self):
        return rag.answer_question("What is the fixture ruling?", compare_schools=True)

    def test_three_retrieved_positions_in_one_validated_response_and_provider_call(self):
        result = self.ask()
        self.assertEqual(result["mode"], "fiqh_comparison")
        self.assertEqual(result["response_schema"], "school_comparison_v1")
        self.assertEqual([s["school"] for s in result["answer_sections"]], list(SCHOOLS))
        self.assertTrue(all(s["status"] == "available" for s in result["answer_sections"]))
        self.provider.assert_called_once()
        self.assertTrue(result["answer_receipt"])
        self.assertIsNone(result["confidence_percent"])
        for section in result["answer_sections"]:
            self.assertEqual(section["answer"], self.outputs[section["school"]])
            self.assertEqual(section["reference_scope"], "topic_level_shared")
            self.assertEqual(section["sources"]["fiqh"][0]["madhhab"], section["title"])
            self.assertEqual(section["scholarly_review"]["status"], "not_completed")

    def test_prompt_has_retrieved_school_notes_and_references_without_certainty_flags(self):
        self.topic["consensus"] = True
        self.topic["rulings"]["hanafi"]["certainty"] = "Very High"
        self.ask()
        prompt = self.provider.call_args.args[0]
        for key in SCHOOLS:
            self.assertIn(key + " fixture position", prompt)
        self.assertIn("[Quran 1:1]", prompt)
        self.assertIn("Do not transfer", prompt)
        self.assertNotIn('"certainty"', prompt)
        self.assertNotIn('"consensus": true', prompt)

    def test_missing_selected_school_never_falls_back_to_another_school(self):
        del self.topic["rulings"]["maliki"]
        self.assertEqual(rag._fiqh_entry_by_id("fixture", "Maliki")["ruling"], {})
        del self.outputs["maliki"]
        result = self.ask()
        self.assertEqual(result["answer_sections"][2]["status"], "unavailable")
        self.assertEqual(result["answer_sections"][2]["sources"], {"fiqh": [], "quran": [], "hadith": []})
        self.assertNotIn("hanafi fixture position", result["answer_sections"][2]["answer"])

    def test_no_school_rulings_does_not_call_provider(self):
        self.topic["rulings"] = {}
        result = self.ask()
        self.provider.assert_not_called()
        self.assertTrue(all(s["status"] == "unavailable" for s in result["answer_sections"]))
        self.assertNotIn("answer_receipt", result)

    def test_invalid_one_school_is_withheld_without_discarding_valid_other_schools(self):
        self.outputs["shafi"] = "Invented fixture [Quran 999:999]."
        result = self.ask()
        self.assertEqual([s["status"] for s in result["answer_sections"]], ["available", "withheld", "available"])
        self.assertNotIn("Invented fixture", result["answer"])

    def test_school_position_needs_its_retrieved_topic_citation(self):
        self.outputs["hanafi"] = "Newly inferred ruling [Quran 1:1]."
        result = self.ask()
        self.assertEqual(result["answer_sections"][0]["status"], "withheld")

    def test_known_consensus_claim_is_withheld_only_in_affected_section(self):
        self.outputs["hanafi"] = "All schools agree [Fixture topic]."
        result = self.ask()
        self.assertEqual(result["answer_sections"][0]["status"], "withheld")
        self.assertNotIn("All schools agree", result["answer"])

    def test_refused_or_null_section_is_not_replaced_with_another_answer(self):
        self.outputs["hanafi"] = None
        result = self.ask()
        self.assertEqual(result["answer_sections"][0]["status"], "withheld")

    def test_malformed_or_extra_or_duplicate_school_output_fails_closed(self):
        duplicate = json.dumps(self.outputs)[:-1] + ', "hanafi": "duplicate"}'
        for raw in ("Not JSON", "[]", duplicate,
                    json.dumps({**self.outputs, "general": "extra"}),
                    json.dumps({"hanafi": self.outputs["hanafi"]})):
            with self.subTest(raw=raw):
                self.provider.side_effect = None
                self.provider.return_value = raw
                result = self.ask()
                self.assertEqual(result["mode"], "low_confidence")
                self.assertNotIn("answer_receipt", result)

    def test_model_cannot_fill_a_school_missing_from_retrieved_material(self):
        del self.topic["rulings"]["maliki"]
        result = self.ask()
        self.assertEqual(result["mode"], "low_confidence")

    def test_explanation_without_a_ruling_is_not_used_to_invent_a_position(self):
        self.topic["rulings"]["maliki"]["ruling"] = ""
        del self.outputs["maliki"]
        self.assertEqual(self.ask()["answer_sections"][2]["status"], "unavailable")

    def test_one_schools_labeled_answer_cannot_be_reassigned_to_another_school(self):
        self.outputs["hanafi"] = self.outputs["maliki"]
        self.assertEqual(self.ask()["answer_sections"][0]["status"], "withheld")

    def test_no_accepted_sections_means_no_passed_check_or_signed_answer(self):
        self.outputs = {key: None for key in SCHOOLS}
        result = self.ask()
        self.assertTrue(all(s["status"] == "withheld" for s in result["answer_sections"]))
        self.assertNotIn("answer_receipt", result)
        self.assertNotIn("citation_validation", result)

    def test_legacy_missing_selected_school_does_not_generate_from_other_sources(self):
        del self.topic["rulings"]["maliki"]
        result = rag.answer_question("What is the fixture ruling?", "Maliki")
        self.provider.assert_not_called()
        self.assertEqual(result["mode"], "low_confidence")

    def test_nonstring_or_oversized_school_output_is_rejected(self):
        for value in ([], 42, "x" * 6001):
            with self.subTest(value_type=type(value).__name__):
                self.outputs["maliki"] = value
                self.assertEqual(self.ask()["mode"], "low_confidence")

    def test_school_header_in_provider_text_cannot_confuse_history_parsing(self):
        self.outputs["hanafi"] += "\n## Maliki\nExtra heading"
        result = self.ask()
        self.assertEqual(result["answer_sections"][0]["status"], "withheld")

    def test_weak_match_does_not_generate_three_speculative_answers(self):
        with patch.object(rag, "classify_topic", return_value=[("fixture", 0.4)]):
            result = self.ask()
        self.provider.assert_not_called()
        self.assertEqual(result["mode"], "low_confidence")

    def test_secondary_unmatched_topic_does_not_become_school_context(self):
        second = copy.deepcopy(self.topic)
        second.update(topic_id="other", topic_name="Other topic")
        second["rulings"]["maliki"]["ruling"] = "UNRELATED SCHOOL NOTE"
        rag.fiqh_topics.append(second)
        with patch.object(rag, "retrieve_fiqh_ruling", return_value=[rag._fiqh_entry_by_id("other", score=0.99)]):
            self.ask()
        self.assertNotIn("UNRELATED SCHOOL NOTE", self.provider.call_args.args[0])

    def test_pipeline_does_not_mutate_original_records(self):
        original = copy.deepcopy(self.topic)
        self.ask()
        self.assertEqual(self.topic, original)

    def test_default_api_without_selection_returns_three_school_sections(self):
        response = self.api_client().post("/ask", json={"question": "What is the fixture ruling?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["mode"], "fiqh_comparison")
        self.assertEqual(len(response.json["answer_sections"]), 3)

    def translate(self, first):
        self.provider.reset_mock()
        with patch.object(rag, "_is_meta_instruction", return_value=True):
            return rag.answer_question("explain in roman urdu", compare_schools=True,
                                       prev_answer=first["answer"], prev_answer_receipt=first.get("answer_receipt"))

    def test_translation_keeps_school_identity_citations_and_new_receipt(self):
        first = self.ask()
        self.outputs = {key: key + " fixture tarjuma [Fixture topic] [Quran 1:1]." for key in SCHOOLS}
        result = self.translate(first)
        self.assertEqual(result["mode"], "fiqh_comparison")
        self.assertEqual(result["answer_sections"][1]["answer"], self.outputs["shafi"])
        self.assertTrue(result["answer_receipt"])

    def test_edited_school_answer_or_changed_ruling_rejected_before_translation(self):
        first = self.ask()
        for changed in ("answer", "source"):
            with self.subTest(changed=changed):
                if changed == "answer":
                    modified = {**first, "answer": first["answer"].replace("hanafi organized", "Edited organized")}
                else:
                    modified = first
                    self.topic["rulings"]["hanafi"]["ruling"] = "Updated fixture"
                result = self.translate(modified)
                self.provider.assert_not_called()
                self.assertEqual(result["mode"], "low_confidence")

    def test_translation_cannot_drop_a_reference_in_one_school(self):
        first = self.ask()
        self.outputs["maliki"] = "maliki fixture tarjuma [Fixture topic]."
        result = self.translate(first)
        self.assertEqual(result["answer_sections"][2]["status"], "withheld")

    def test_unavailable_school_stays_unavailable_during_translation(self):
        del self.topic["rulings"]["maliki"]
        del self.outputs["maliki"]
        first = self.ask()
        result = self.translate(first)
        self.assertEqual(result["answer_sections"][2]["status"], "unavailable")

    def test_legacy_single_school_proof_is_preserved_after_switch_to_direct_chat(self):
        self.provider.side_effect = None
        self.provider.return_value = "Fixture answer [Fixture topic] [Quran 1:1]."
        first = rag.answer_question("What is the fixture ruling?", "Hanafi")
        self.provider.return_value = "Fixture tarjuma [Fixture topic] [Quran 1:1]."
        result = self.translate(first)
        self.assertEqual(result["mode"], "reexpress")
        self.assertTrue(result["answer_receipt"])


if __name__ == "__main__":
    unittest.main()
