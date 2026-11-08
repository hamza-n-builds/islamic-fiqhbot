"""Read-only local reference resolution audit; not scholarly verification.

Writes a JSON report containing identifiers/counts, never provider credentials or
conversation contents. Missing references are reported, never guessed/replaced.
"""
from collections import Counter
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

import yaml

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from source_records import load_hadith_records, normalize_hadith_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(),
                        help="Evidence date as YYYY-MM-DD; use the client's local date")
    args = parser.parse_args()
    data = BACKEND / "data"
    topics = yaml.safe_load((data / "fiqh_topics_complete_expanded.yaml").read_text(encoding="utf-8"))
    quran = json.loads((data / "quran_trilingual_clean.json").read_text(encoding="utf-8"))
    hadith = json.loads((data / "sahih_bukhari_muslim.json").read_text(encoding="utf-8"))
    other = json.loads((data / "other_hadith.json").read_text(encoding="utf-8"))
    quran_lookup = {(v["chapter"], v["ayah"]): v for v in quran}
    corpus = load_hadith_records(data / "sahih_bukhari_muslim.json", data / "other_hadith.json",
                                data / "hadith_identity_registry.json")
    hadith_lookup = corpus.lookup
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
        "date": args.date.isoformat(), "scope": "Pinned canonical identity and text availability; primary-page checks recorded in the registry; no semantic or scholarly certification",
        "topics": len(topics), "quran_records": len(quran), "main_hadith_records": len(hadith),
        "supplementary_hadith_records": len(other), "scholar_review_statuses": dict(reviews),
        "reference_resolution": "incomplete" if any(issues.values()) else "complete",
        "issues": issues,
        "canonical_identity_audit": corpus.audit,
        "generation_holds": [{"source": row["source"], "hadith_no": row["hadith_no"],
                              "reported_grade": row.get("reported_grade"), "reference_url": row["reference_url"]}
                             for row in corpus.records if not row["generation_eligible"]],
        "runtime_behavior": "Lookup/search use the pinned canonical registry only. Legacy corpus integer keys never resolve canonical references implicitly. Missing/textless/held sources cannot enter generation context.",
        "dataset_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(data.iterdir()) if p.suffix in {".json", ".yaml"}},
        "religious_accuracy_reviewed": False,
        "ruling_support_review_complete": False,
        "production_ready": False,
    }
    target = BACKEND.parent / "replica/evidence/source-record-audit.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"topics": len(topics), "review_statuses": dict(reviews), "reference_resolution": report["reference_resolution"],
                      "issue_counts": {key: len(value) for key, value in issues.items()}, "report": str(target)}, indent=2))
    return 1 if any(issues.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
