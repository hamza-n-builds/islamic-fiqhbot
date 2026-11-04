"""Resolve published hadith identities to pinned, owner-provided corpus rows.

Legacy integer keys are not a canonical numbering scheme. Only registered text
identities enter runtime lookup/search. Identity checks are not scholarly review.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unicodedata
from urllib.parse import urlsplit

COLLECTION_PATHS = {"Sahih Bukhari": "bukhari", "Sahih Muslim": "muslim",
                    "Jami at-Tirmidhi": "tirmidhi", "Sunan an-Nasa'i": "nasai",
                    "Sunan Abi Dawud": "abudawud"}
ALIASES = {"sahih bukhari": "Sahih Bukhari", "sahih al bukhari": "Sahih Bukhari",
           "sahih muslim": "Sahih Muslim", "sahih al muslim": "Sahih Muslim"}


class SourceRegistryError(ValueError):
    """The source identity registry cannot be used safely."""


def normalize_hadith_source(source):
    if source is not None and not isinstance(source, str):
        raise SourceRegistryError("Hadith collection names must be text")
    value = re.sub(r"\s+", " ", (source or "").strip().casefold().replace("-", " "))
    return ALIASES.get(value, (source or "").strip())


def row_fingerprint(row):
    encoded = json.dumps(row, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalized_arabic(text):
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"صلى\s*الله\s*عليه\s*وسلم", "", text)
    return "".join(char for char in text if "\u0621" <= char <= "\u064a" and char != "\u0640")


def arabic_fingerprint(text):
    if not isinstance(text, str):
        raise SourceRegistryError("A registered source has no Arabic text identity")
    normalized = normalized_arabic(text)
    if not normalized:
        raise SourceRegistryError("A registered source has no Arabic text identity")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_hadith_records(main_path, supplementary_path, registry_path):
    try:
        main = json.loads(Path(main_path).read_text(encoding="utf-8"))
        other = json.loads(Path(supplementary_path).read_text(encoding="utf-8"))
        registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SourceRegistryError("Restore the local hadith corpus and canonical registry files before starting") from error
    if not isinstance(main, list) or not isinstance(other, list) or not isinstance(registry, dict):
        raise SourceRegistryError("Unexpected corpus/registry structure")
    if any(not isinstance(row, dict) for row in [*main, *other]):
        raise SourceRegistryError("A corpus row is not an object")
    entries = registry.get("entries")
    if registry.get("schema_version") != 1 or not isinstance(entries, list) or not entries:
        raise SourceRegistryError("The canonical hadith registry is empty or unsupported")
    corpora = {"sahih_bukhari_muslim.json": main, "other_hadith.json": other}
    fingerprints = {name: {row_fingerprint(row): row for row in rows} for name, rows in corpora.items()}
    raw_keys = Counter((normalize_hadith_source(row.get("source")), str(row.get("hadith_no"))) for row in [*main, *other])
    records, lookup = [], {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise SourceRegistryError("Invalid canonical registry entry")
        if not isinstance(entry.get("source"), str):
            raise SourceRegistryError("Canonical source must be text")
        source = normalize_hadith_source(entry.get("source"))
        number = entry.get("hadith_no")
        if source not in COLLECTION_PATHS or not isinstance(number, str) or not re.fullmatch(r"[1-9][0-9]*[a-z]?", number):
            raise SourceRegistryError("Canonical source/number must identify an explicit published narration")
        key = (source, number)
        if key in lookup:
            raise SourceRegistryError("Duplicate canonical hadith identity: " + source + " #" + number)
        url = entry.get("reference_url", "")
        if not isinstance(url, str):
            raise SourceRegistryError("Published reference URL must be text")
        parsed = urlsplit(url)
        if url != f"https://sunnah.com/{COLLECTION_PATHS[source]}:{number}" or parsed.query or parsed.fragment:
            raise SourceRegistryError("Published reference URL does not match the canonical identity")
        verification = entry.get("verification", {})
        if (not isinstance(verification, dict)
                or entry.get("identity_status") != "primary_arabic_text_matched"
                or verification.get("primary_page_checked") is not True
                or entry.get("ruling_support_review") != "pending"):
            raise SourceRegistryError("Text identity evidence is missing or incorrectly presented as ruling approval")
        label = verification.get("primary_reference", "")
        if not isinstance(label, str) or label.split()[-1:] != [number]:
            raise SourceRegistryError("Published page reference does not identify this exact narration variant")
        eligible = entry.get("generation_eligible")
        grade = entry.get("reported_grade", "")
        if type(eligible) is not bool or not isinstance(grade, str) or (grade.casefold().startswith("shadh") and eligible):
            raise SourceRegistryError("Source generation eligibility requires explicit, conservative grade review")
        row = fingerprints.get(entry.get("local_file"), {}).get(entry.get("local_row_sha256"))
        if row is None or normalize_hadith_source(row.get("source")) != source:
            raise SourceRegistryError("A pinned local source row changed or is missing: " + source + " #" + number)
        original_grade = row.get("grade") or ""
        if isinstance(original_grade, str) and original_grade.casefold().startswith("shadh") and eligible:
            raise SourceRegistryError("The pinned source grade requires a generation hold until qualified grade review")
        if not isinstance(row.get("text_en"), str) or not row["text_en"].strip():
            raise SourceRegistryError("A registered narration lacks the English text used by generation")
        if arabic_fingerprint(row.get("text_ar", "")) != verification.get("primary_arabic_normalized_sha256"):
            raise SourceRegistryError("Arabic source identity no longer matches the checked published page")
        record = {**row, "source": source, "hadith_no": number, "reference_url": url,
                  "generation_eligible": eligible, "reported_grade": grade or row.get("grade"),
                  "source_identity": {"status": "primary_arabic_text_matched", "local_row_sha256": entry["local_row_sha256"],
                                      "checked_on": verification.get("date"), "ruling_support_review": "pending"}}
        records.append(record)
        lookup[key] = record
    return SimpleNamespace(records=records, lookup=lookup, audit={
        "raw_main_records": len(main), "raw_supplementary_records": len(other),
        "legacy_duplicate_key_groups": sum(count > 1 for count in raw_keys.values()),
        "legacy_duplicate_key_rows": sum(count - 1 for count in raw_keys.values() if count > 1),
        "canonical_registered_records": len(records),
        "generation_eligible_records": sum(row["generation_eligible"] for row in records),
    })
