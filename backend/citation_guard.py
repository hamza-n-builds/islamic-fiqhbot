"""Citation membership checks and signed response provenance.

These checks cannot determine whether a claim follows from a source or whether
a religious ruling is correct. They must not be described as scholarly review.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time

MAX_ANSWER_LENGTH = 20000
MAX_RECEIPT_LENGTH = 8192
MAX_CITATIONS = 32
RECEIPT_TTL = 7 * 24 * 60 * 60
BRACKETS = re.compile(r"\[([^\[\]\n]+)\]")
BARE_REFERENCE = re.compile(
    r"\b(?:qur[’']?an\s*\d+\s*:\s*\d+|(?:sahih\s+(?:al[- ]?)?)?(?:bukhari|muslim|tirmidhi|nasa[’']?i|abu\s+dawud)\s*#?\s*\d+)",
    re.IGNORECASE,
)
SCHOOL_LABELS = {"hanafi", "shafi'i", "shafi", "maliki", "general"}


class CitationError(ValueError):
    """A machine-readable reason to withhold a generated response."""


def _key(tag):
    return " ".join(tag.split()).casefold()


def validate_citations(answer, allowed, *, expected=None):
    """Reject the whole answer on an invalid reference; never remove its proof.

    `allowed` contains only tags whose actual source text was supplied in this
    generation request. Returns normalized text and the distinct cited tags.
    """
    if not isinstance(answer, str) or not answer.strip() or len(answer) > MAX_ANSWER_LENGTH:
        raise CitationError("invalid_output")
    permitted = {_key(tag): tag for tag in allowed}
    cited = []

    def replace(match):
        tag = match.group(0)
        canonical = permitted.get(_key(tag))
        if canonical:
            if canonical not in cited:
                cited.append(canonical)
            return canonical
        if _key(match.group(1)) in SCHOOL_LABELS:
            return match.group(1).strip()  # A label is not evidence.
        raise CitationError("unprovided_citation")

    normalized = BRACKETS.sub(replace, answer).strip()
    remainder = BRACKETS.sub("", normalized)
    if "[" in remainder or "]" in remainder:
        raise CitationError("malformed_citation")
    if BARE_REFERENCE.search(remainder) or re.search(r"https?://", remainder, re.IGNORECASE):
        raise CitationError("unbracketed_reference")
    if not cited or len(cited) > MAX_CITATIONS:
        raise CitationError("missing_citation")
    if not re.search(r"\w", remainder):
        raise CitationError("invalid_output")
    if expected is not None and set(cited) != set(expected):
        raise CitationError("changed_citations")
    return normalized, tuple(cited)


class ResponseReceipts:
    """Bind the exact server response and its citation tags to an opaque proof."""

    def __init__(self, secret=None):
        configured = os.environ.get("FIQHBOT_RESPONSE_SECRET", "") if secret is None else secret
        if configured and len(configured.encode("utf-8")) < 32:
            raise ValueError("FIQHBOT_RESPONSE_SECRET must contain at least 32 bytes when configured")
        self._secret = hashlib.sha256(configured.encode("utf-8")).digest() if configured else secrets.token_bytes(32)

    def issue(self, answer, tags, context_digest, *, now=None):
        payload = {"v": 1, "answer": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
                   "tags": list(tags), "context": context_digest,
                   "expires": int(time.time() if now is None else now) + RECEIPT_TTL}
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
        signature = hmac.new(self._secret, encoded, hashlib.sha256).hexdigest()
        token = encoded.decode("ascii") + "." + signature
        if len(token) > MAX_RECEIPT_LENGTH:
            raise CitationError("invalid_receipt_size")
        return token

    def verify(self, answer, token, *, now=None):
        if not isinstance(answer, str) or len(answer) > MAX_ANSWER_LENGTH or not isinstance(token, str) or not token or len(token) > MAX_RECEIPT_LENGTH:
            return None
        try:
            encoded, signature = token.split(".")
            expected = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return None
            data = json.loads(base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True))
            current = int(time.time() if now is None else now)
            if (data.get("v") != 1 or type(data.get("expires")) is not int
                    or not current < data["expires"] <= current + RECEIPT_TTL + 60
                    or not hmac.compare_digest(data.get("answer", ""), hashlib.sha256(answer.encode("utf-8")).hexdigest())):
                return None
            tags = data.get("tags")
            if not isinstance(tags, list) or not 0 < len(tags) <= MAX_CITATIONS:
                return None
            if any(not isinstance(tag, str) or not 0 < len(tag) <= 256 for tag in tags):
                return None
            if len(set(tags)) != len(tags):
                return None
            if not isinstance(data.get("context"), str) or not re.fullmatch(r"[0-9a-f]{64}", data["context"]):
                return None
            return tuple(tags), data["context"]
        except (ValueError, TypeError, UnicodeError, AttributeError):
            return None
