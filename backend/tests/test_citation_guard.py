"""Deterministic citation/provenance tests; no model, credentials or network."""
import base64
import importlib.util
import json
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("citation_guard_tests", Path(__file__).parents[1] / "citation_guard.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class CitationGuardTests(unittest.TestCase):
    allowed = {"[Quran 1:1]", "[Sahih Bukhari #1]", "[Fixture topic]"}

    def test_valid_tags_are_preserved_and_deduplicated_in_inventory(self):
        text = "Fixture [Quran 1:1]. More [Quran 1:1] [Sahih Bukhari #1]."
        normalized, tags = guard.validate_citations(text, self.allowed)
        self.assertEqual(normalized, text)
        self.assertEqual(tags, ("[Quran 1:1]", "[Sahih Bukhari #1]"))

    def test_case_variation_resolves_to_the_actual_context_tag(self):
        text, tags = guard.validate_citations("Fixture [qUrAn 1:1].", self.allowed)
        self.assertEqual(text, "Fixture [Quran 1:1].")
        self.assertEqual(tags, ("[Quran 1:1]",))

    def test_unprovided_citations_reject_entire_response(self):
        for tag in ("[Quran 999:999]", "[Sahih Muslim #999]", "[Unknown topic]", "[Anything #9]"):
            with self.subTest(tag=tag), self.assertRaisesRegex(guard.CitationError, "unprovided_citation"):
                guard.validate_citations("Fixture [Quran 1:1] " + tag, self.allowed)

    def test_school_label_does_not_count_as_a_reference(self):
        with self.assertRaisesRegex(guard.CitationError, "missing_citation"):
            guard.validate_citations("[Hanafi] Fixture answer.", self.allowed)
        text, tags = guard.validate_citations("[Hanafi] Fixture [Fixture topic].", self.allowed)
        self.assertEqual(text, "Hanafi Fixture [Fixture topic].")
        self.assertEqual(tags, ("[Fixture topic]",))

    def test_empty_invalid_and_oversized_outputs_fail_closed(self):
        for answer in (None, [], "", "   ", "x" * 20001):
            with self.subTest(type=type(answer).__name__), self.assertRaises(guard.CitationError):
                guard.validate_citations(answer, self.allowed)

    def test_uncited_output_is_rejected(self):
        with self.assertRaisesRegex(guard.CitationError, "missing_citation"):
            guard.validate_citations("Fixture answer without a reference.", self.allowed)

    def test_citation_only_is_not_a_substantive_response(self):
        with self.assertRaisesRegex(guard.CitationError, "invalid_output"):
            guard.validate_citations("[Quran 1:1].", self.allowed)

    def test_broken_brackets_are_rejected(self):
        for ending in (" [Quran 9:9", " Quran 9:9]", " [[Quran 1:1]]"):
            with self.subTest(ending=ending), self.assertRaises(guard.CitationError):
                guard.validate_citations("Fixture [Quran 1:1]." + ending, self.allowed)

    def test_bare_references_and_urls_cannot_bypass_the_bracket_gate(self):
        for extra in ("Quran 999:999", "Qur'an 2:3", "Sahih Bukhari #99", "Sahih Muslim 88", "https://unprovided.example/source"):
            with self.subTest(extra=extra), self.assertRaisesRegex(guard.CitationError, "unbracketed_reference"):
                guard.validate_citations("Fixture [Quran 1:1]. " + extra, self.allowed)

    def test_translation_cannot_drop_or_add_reference_identities(self):
        expected = {"[Quran 1:1]", "[Fixture topic]"}
        with self.assertRaisesRegex(guard.CitationError, "changed_citations"):
            guard.validate_citations("Fixture [Quran 1:1].", self.allowed, expected=expected)
        with self.assertRaisesRegex(guard.CitationError, "unprovided_citation"):
            guard.validate_citations("Fixture [Quran 1:1] [Quran 2:2].", expected, expected=expected)
        _, tags = guard.validate_citations("Fixture [Fixture topic] [Quran 1:1].", self.allowed, expected=expected)
        self.assertEqual(set(tags), expected)


class ResponseReceiptTests(unittest.TestCase):
    def setUp(self):
        self.signer = guard.ResponseReceipts("test-only-secret-at-least-32-bytes-long")
        self.answer = "Fixture answer [Quran 1:1]."
        self.tags = ("[Quran 1:1]",)
        self.fingerprint = "a" * 64
        self.token = self.signer.issue(self.answer, self.tags, self.fingerprint, now=1000)

    def test_valid_receipt_binds_answer_references_and_context(self):
        self.assertEqual(self.signer.verify(self.answer, self.token, now=1001), (self.tags, self.fingerprint))

    def test_editing_answer_invalidates_proof(self):
        self.assertIsNone(self.signer.verify(self.answer + " Added claim.", self.token, now=1001))

    def test_editing_receipt_payload_invalidates_proof(self):
        encoded, signature = self.token.split(".")
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        payload["tags"] = ["[Quran 2:2]"]
        changed = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        self.assertIsNone(self.signer.verify(self.answer, changed + "." + signature, now=1001))

    def test_other_key_cannot_accept_receipt(self):
        other = guard.ResponseReceipts("another-test-secret-at-least-32-bytes")
        self.assertIsNone(other.verify(self.answer, self.token, now=1001))

    def test_same_configured_secret_survives_a_new_process_instance(self):
        same = guard.ResponseReceipts("test-only-secret-at-least-32-bytes-long")
        self.assertEqual(same.verify(self.answer, self.token, now=1001), (self.tags, self.fingerprint))

    def test_default_keys_are_process_local(self):
        first, second = guard.ResponseReceipts(""), guard.ResponseReceipts("")
        token = first.issue(self.answer, self.tags, self.fingerprint, now=1000)
        self.assertIsNone(second.verify(self.answer, token, now=1001))

    def test_expired_receipt_is_rejected(self):
        self.assertIsNone(self.signer.verify(self.answer, self.token, now=1000 + guard.RECEIPT_TTL))

    def test_bad_receipts_are_rejected_without_exceptions(self):
        for token in (None, [], "", "a.b.c", "a.x", "\u00e9.x", "x" * 8193):
            with self.subTest(type=type(token).__name__):
                self.assertIsNone(self.signer.verify(self.answer, token, now=1001))

    def test_short_explicit_secret_is_rejected(self):
        with self.assertRaises(ValueError):
            guard.ResponseReceipts("short")


if __name__ == "__main__":
    unittest.main()
