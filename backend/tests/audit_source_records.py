"""Read-only local reference resolution audit; not scholarly verification.

Writes a JSON report containing identifiers/counts, never provider credentials or
conversation contents. Missing references are reported, never guessed/replaced.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import yaml

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from rag_engine import normalize_hadith_source


def main():
    data = BACKEND / "data"
    topics = yaml.safe_load((data / "fiqh_topics_complete_expanded.yaml").read_text(encoding="utf-8"))
    quran = json.loads((data / "quran_trilingual_clean.json").read_text(encoding="utf-8"))
    hadith = json.loads((data / "sahih_bukhari_muslim.json").read_text(encoding="utf-8"))
    other = json.loads((data / "other_hadith.json").read_text(encoding="utf-8"))
    quran_lookup = {(v["chapter"], v["ayah"]): v for v in quran}
    hadith_lookup = {(normalize_hadith_source(h["source"]), str(h["hadith_no"])): h for h in [*hadith, *other]}
    missing_quran, missing_hadith, empty_quran, empty_hadith = [], [], [], []
    for topic in topics:
        refs = topic.get("references", {}) or {}
        for ref in refs.get("quran", []) or []:
            identifier = {"topic_id": topic["topic_id"], "chapter": ref.get("chapter"), "ayah": ref.get("ayah")}
            record = quran_lookup.get((ref.get("chapter"), ref.get("ayah")))
            if record is None:
                missing_quran.append(identifier)
            elif not isinstance(record.get("english"), str) or not record["english"].strip():
                empty_quran.append(identifier)
        for ref in refs.get("hadith", []) or []:
            identifier = {"topic_id": topic["topic_id"], "source": ref.get("source"), "hadith_no": ref.get("hadith_no")}
            record = hadith_lookup.get((normalize_hadith_source(ref.get("source", "")), str(ref.get("hadith_no", ""))))
            if record is None:
                missing_hadith.append(identifier)
            elif not isinstance(record.get("text_en"), str) or not record["text_en"].strip():
                empty_hadith.append(identifier)
    reviews = Counter(str(t.get("scholar_review") or "unspecified") for t in topics)
    issues = {"missing_quran": missing_quran, "missing_hadith": missing_hadith,
              "referenced_quran_without_english": empty_quran, "referenced_hadith_without_english": empty_hadith}
    report = {
        "date": "2026-11-04", "scope": "Local record resolution/text availability only; no semantic or scholarly certification",
        "topics": len(topics), "quran_records": len(quran), "main_hadith_records": len(hadith),
        "supplementary_hadith_records": len(other), "scholar_review_statuses": dict(reviews),
        "reference_resolution": "incomplete" if any(issues.values()) else "complete",
        "issues": issues,
        "runtime_behavior": "Missing/textless records are excluded from generation context; references outside that context reject the whole generated answer.",
        "dataset_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(data.iterdir()) if p.suffix in {".json", ".yaml"}},
        "religious_accuracy_reviewed": False,
    }
    target = BACKEND.parent / "replica/evidence/source-record-audit.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"topics": len(topics), "review_statuses": dict(reviews), "reference_resolution": report["reference_resolution"],
                      "issue_counts": {key: len(value) for key, value in issues.items()}, "report": str(target)}, indent=2))
    return 1 if any(issues.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
