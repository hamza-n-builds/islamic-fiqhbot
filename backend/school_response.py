"""Strict organizer output and deterministic three-school response serialization."""
import json
import re

from citation_guard import CitationError, MAX_ANSWER_LENGTH

SCHOOLS = (("hanafi", "Hanafi"), ("shafi", "Shafi'i"), ("maliki", "Maliki"))
SCHEMA = "school_comparison_v1"
MODE = "fiqh_comparison"
MAX_SECTION_LENGTH = 6000
HEADERS = re.compile(r"^## (Hanafi|Shafi'i|Maliki)\n", re.MULTILINE)
NOTICES = {
    "unavailable": {
        "en": "This school's position is not available in the retrieved material. Please consult a qualified scholar.",
        "roman": "Retrieved material mein is school ka mauqif available nahi hai. Kisi mustanad aalim se rujoo karein.",
        "ur": "دستیاب مواد میں اس فقہی مکتب کا موقف موجود نہیں۔ کسی مستند عالم سے رجوع کریں۔",
        "ar": "موقف هذا المذهب غير متوفر في المادة المسترجعة. يرجى الرجوع إلى عالم مؤهل.",
    },
    "withheld": {
        "en": "I couldn't validate this school's organized answer against its supplied material. Please clarify your question or consult a qualified scholar.",
        "roman": "Is school ke organized jawab ko supplied material ke saath validate nahi kiya ja saka. Sawal wazeh karein ya kisi mustanad aalim se rujoo karein.",
        "ur": "اس فقہی مکتب کے مرتب جواب کی فراہم کردہ مواد کے ساتھ توثیق نہیں ہو سکی۔ سوال واضح کریں یا مستند عالم سے رجوع کریں۔",
        "ar": "تعذر التحقق من إجابة هذا المذهب مقابل المادة المقدمة. يرجى توضيح السؤال أو الرجوع إلى عالم مؤهل.",
    },
}


def parse_school_output(raw, expected):
    if not isinstance(raw, str) or len(raw) > MAX_ANSWER_LENGTH:
        raise CitationError("invalid_school_output")
    fenced = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", raw.strip(), re.DOTALL)
    text = fenced[1] if fenced else raw

    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise CitationError("duplicate_school_key")
            out[key] = value
        return out

    try:
        values = json.loads(text, object_pairs_hook=unique)
    except (ValueError, TypeError) as error:
        raise CitationError("invalid_school_output") from error
    if not isinstance(values, dict) or set(values) != set(expected):
        raise CitationError("unexpected_school_keys")
    if any(value is not None and (not isinstance(value, str) or len(value) > MAX_SECTION_LENGTH)
           for value in values.values()):
        raise CitationError("invalid_school_output")
    return values


def validate_school_wording(answer, school):
    if HEADERS.search(answer):
        raise CitationError("nested_school_header")
    patterns = {"hanafi": r"\bhanafi\b|حنفی|حنفي", "shafi": r"\bshafi(?:[’']i)?\b|شافعی|شافعي",
                "maliki": r"\bmaliki\b|مالکی|مالكي"}
    if any(re.search(pattern, answer, re.IGNORECASE) for key, pattern in patterns.items() if key != school):
        raise CitationError("cross_school_wording")


def flatten_sections(sections):
    if [s["school"] for s in sections] != [key for key, _ in SCHOOLS]:
        raise CitationError("invalid_school_order")
    text = "\n\n".join(f"## {title}\n{section['answer'].strip()}" for section, (_, title) in zip(sections, SCHOOLS))
    if len(text) > MAX_ANSWER_LENGTH:
        raise CitationError("invalid_output")
    return text


def split_sections(answer):
    matches = list(HEADERS.finditer(answer))
    if len(matches) != 3 or matches[0].start() != 0 or [m[1] for m in matches] != [title for _, title in SCHOOLS]:
        raise CitationError("invalid_comparison_history")
    sections = []
    for index, ((key, title), match) in enumerate(zip(SCHOOLS, matches)):
        end = matches[index + 1].start() if index < 2 else len(answer)
        body = answer[match.end():end].rstrip("\n")
        status = next((status for status, messages in NOTICES.items() if body in messages.values()), "available")
        sections.append({"school": key, "title": title, "answer": body, "status": status})
    if flatten_sections(sections) != answer:
        raise CitationError("invalid_comparison_history")
    return sections
