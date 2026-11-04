"""Canonical IDs must return the verified local narration, not a legacy key hit."""
import json
from pathlib import Path
import unittest

from test_api_boundary import load_api

DATA = Path(__file__).resolve().parents[1] / "data"
ROWS = json.loads((DATA / "sahih_bukhari_muslim.json").read_text(encoding="utf-8"))


def local_text(source, legacy_number):
    matches = [row for row in ROWS if row["source"] == source and str(row["hadith_no"]) == legacy_number]
    if len(matches) != 1:
        raise AssertionError("Test locator must be unambiguous")
    return matches[0]["text_en"]


class SourceIdentityRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api, _, _ = load_api()

    def setUp(self):
        self.client = self.api.app.test_client()

    def test_bukhari_1395_resolves_existing_local_narration(self):
        reply = self.client.get("/hadith-text", query_string={"source": "Sahih Bukhari", "number": "1395"})
        self.assertTrue(reply.json["found"])
        self.assertEqual(reply.json["text_en"], local_text("Sahih Bukhari", "1413"))

    def test_muslim_11a_uses_faith_narration_instead_of_introduction_11(self):
        reply = self.client.get("/hadith-text", query_string={"source": "Sahih Muslim", "number": "11a"})
        self.assertTrue(reply.json["found"])
        self.assertEqual(reply.json["text_en"], local_text("Sahih Muslim", "109"))

    def test_bukhari_5590_is_not_the_legacy_5590_goat_narration(self):
        reply = self.client.get("/hadith-text", query_string={"source": "Sahih Bukhari", "number": "5590"})
        self.assertTrue(reply.json["found"])
        self.assertEqual(reply.json["text_en"], local_text("Sahih Bukhari", "5649"))

    def test_ambiguous_muslim_base_11_is_not_silently_mapped_to_introduction(self):
        reply = self.client.get("/hadith-text", query_string={"source": "Sahih Muslim", "number": "11"})
        self.assertFalse(reply.json["found"])


if __name__ == "__main__":
    unittest.main()
