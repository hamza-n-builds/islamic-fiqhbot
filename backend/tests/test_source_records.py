"""Source identity, ambiguity and preservation regressions. No external calls."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

BACKEND = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_record_test_module", BACKEND / "source_records.py")
sources = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sources)


class SourceRecordTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="fiqhbot sources ")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.main = self.folder / "main.json"
        self.other = self.folder / "other.json"
        self.registry = self.folder / "registry.json"
        self.row = {"source": "Sahih Muslim", "hadith_no": "109", "chapter": "Fixture Faith",
                    "text_ar": "\u0627\u0628\u062c", "text_en": "Fixture original narration"}
        self.rows = [self.row, {**self.row, "text_ar": "\u062f\u0647\u0648", "text_en": "Wrong last duplicate"}]
        self.entry = {"source": "Sahih Muslim", "hadith_no": "11a", "local_file": "sahih_bukhari_muslim.json",
                      "local_row_sha256": sources.row_fingerprint(self.row), "reference_url": "https://sunnah.com/muslim:11a",
                      "identity_status": "primary_arabic_text_matched", "ruling_support_review": "pending",
                      "generation_eligible": True,
                      "verification": {"primary_page_checked": True, "primary_reference": "Sahih Muslim 11a",
                                       "date": "2026-11-04", "primary_arabic_normalized_sha256": sources.arabic_fingerprint(self.row["text_ar"])}}

    def load(self, entries=None):
        self.main.write_text(json.dumps(self.rows), encoding="utf-8")
        self.other.write_text("[]", encoding="utf-8")
        self.registry.write_text(json.dumps({"schema_version": 1, "entries": entries or [self.entry]}), encoding="utf-8")
        return sources.load_hadith_records(self.main, self.other, self.registry)

    def test_exact_fingerprint_resolves_colliding_legacy_key_without_last_winner(self):
        result = self.load()
        self.assertEqual(result.lookup[("Sahih Muslim", "11a")]["text_en"], "Fixture original narration")
        self.assertEqual(result.audit["legacy_duplicate_key_rows"], 1)
        self.assertEqual(len(result.lookup), 1)
        self.assertNotIn(("Sahih Muslim", "109"), result.lookup)

    def test_corpus_content_is_not_modified_by_loading(self):
        self.load()
        before = self.main.read_bytes()
        sources.load_hadith_records(self.main, self.other, self.registry)
        self.assertEqual(self.main.read_bytes(), before)

    def test_missing_registry_fails_closed(self):
        with self.assertRaises(sources.SourceRegistryError):
            sources.load_hadith_records(self.main, self.other, self.registry)

    def test_changed_pinned_source_row_is_rejected(self):
        self.row["text_en"] = "Changed translation"
        with self.assertRaisesRegex(sources.SourceRegistryError, "changed or is missing"):
            self.load()

    def test_missing_english_is_not_replaced_with_generated_text(self):
        self.row["text_en"] = ""
        self.entry["local_row_sha256"] = sources.row_fingerprint(self.row)
        with self.assertRaisesRegex(sources.SourceRegistryError, "lacks the English"):
            self.load()

    def test_arabic_identity_must_match_even_after_a_fingerprint_edit(self):
        self.row["text_ar"] = "\u0643\u0644\u0645"
        self.entry["local_row_sha256"] = sources.row_fingerprint(self.row)
        with self.assertRaisesRegex(sources.SourceRegistryError, "Arabic source identity"):
            self.load()

    def test_duplicate_canonical_keys_are_rejected(self):
        with self.assertRaisesRegex(sources.SourceRegistryError, "Duplicate canonical"):
            self.load([self.entry, copy.deepcopy(self.entry)])

    def test_different_reference_url_is_rejected(self):
        for url in ("https://untrusted.example/muslim:11a", "https://sunnah.com/muslim:11b", "https://sunnah.com/muslim:11a?override=1"):
            with self.subTest(url=url), self.assertRaises(sources.SourceRegistryError):
                self.entry["reference_url"] = url
                self.load()

    def test_ambiguous_base_number_cannot_reuse_variant_evidence(self):
        self.entry["hadith_no"] = "11"
        self.entry["reference_url"] = "https://sunnah.com/muslim:11"
        with self.assertRaisesRegex(sources.SourceRegistryError, "exact narration variant"):
            self.load()

    def test_path_outside_known_corpora_is_never_read(self):
        self.entry["local_file"] = "../../private.env"
        with self.assertRaises(sources.SourceRegistryError):
            self.load()

    def test_source_identity_is_not_promoted_to_scholarly_approval(self):
        self.entry["ruling_support_review"] = "approved"
        with self.assertRaisesRegex(sources.SourceRegistryError, "ruling approval"):
            self.load()

    def test_unchecked_primary_page_is_rejected(self):
        self.entry["verification"]["primary_page_checked"] = False
        with self.assertRaises(sources.SourceRegistryError):
            self.load()

    def test_reported_shadh_source_requires_generation_hold(self):
        self.entry["reported_grade"] = "Shadh (Al-Albani)"
        with self.assertRaisesRegex(sources.SourceRegistryError, "grade review"):
            self.load()
        self.entry["generation_eligible"] = False
        result = self.load()
        self.assertEqual(result.audit["generation_eligible_records"], 0)
        self.assertFalse(result.lookup[("Sahih Muslim", "11a")]["generation_eligible"])

    def test_collection_aliases_are_explicit(self):
        self.assertEqual(sources.normalize_hadith_source("Sahih al-Bukhari"), "Sahih Bukhari")
        self.assertEqual(sources.normalize_hadith_source("Fictional Muslim"), "Fictional Muslim")

    def test_omitting_registry_grade_cannot_remove_a_hold_on_the_pinned_source(self):
        self.row["grade"] = "Shadh (Al-Albani)"
        self.entry["local_row_sha256"] = sources.row_fingerprint(self.row)
        with self.assertRaisesRegex(sources.SourceRegistryError, "pinned source grade"):
            self.load()


class RegisteredCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = sources.load_hadith_records(BACKEND / "data/sahih_bukhari_muslim.json",
                                               BACKEND / "data/other_hadith.json",
                                               BACKEND / "data/hadith_identity_registry.json")

    def test_all_registered_primary_identities_resolve_without_legacy_fallback(self):
        self.assertEqual(len(self.corpus.lookup), 38)
        self.assertEqual(self.corpus.audit["generation_eligible_records"], 37)
        self.assertEqual(self.corpus.audit["legacy_duplicate_key_rows"], 702)
        for row in self.corpus.records:
            self.assertTrue(row["text_en"].strip())
            self.assertEqual(row["source_identity"]["ruling_support_review"], "pending")

    def test_variant_and_general_zakat_narrations_have_published_urls(self):
        for key, url in ((("Sahih Muslim", "11a"), "https://sunnah.com/muslim:11a"),
                         (("Sahih Bukhari", "1395"), "https://sunnah.com/bukhari:1395")):
            self.assertEqual(self.corpus.lookup[key]["reference_url"], url)


if __name__ == "__main__":
    unittest.main()
