"""Limits on unreviewed claims shared by response generation and presentation.

Reference membership is a mechanical check, not answer accuracy or fiqh approval.
There is no completed, independently verified review workflow in this application.
"""
import re
import unicodedata

from citation_guard import CitationError

REVIEW_SCOPE = "answer_and_ruling_support"
CITATION_SCOPE = "provided_reference_membership"
STATUS_NOTE = "Matching supplied references does not verify the answer's accuracy."
REVIEW_INSTRUCTION = (
    "The dataset notes have not been independently reviewed for ruling support. "
    "Do not claim consensus, ijma, unanimity, or agreement of all schools. "
    "A dataset flag is not evidence of scholarly approval or disagreement. "
    "Only describe the individual school positions actually supplied."
)

# A deliberately conservative wording guard, not a semantic/scholarly verifier.
# It also withholds definitions/negations containing these terms until an actual
# reviewed consensus source workflow exists. Paraphrases can still evade it.
_CONSENSUS_WORDING = re.compile(
    r"\b(?:consensus|unanim\w*|ijma\w*)\b"
    r"|\b(?:all|every|three|both)\s+(?:(?:the|major|three|four)\s+){0,2}"
    r"(?:madhhabs?|schools(?:\s+of\s+thought)?|scholars|jurists)\s+"
    r"(?:(?:are|have|do|in)\s+)?(?:agree\w*|agreement|hold\b|permit\w*|prohibit\w*)"
    r"|\b(?:tamam|tamaam|sab|saare|sare)\s+(?:major\s+)?"
    r"(?:masalik|madhhabs?|schools|ulama)\s+(?:bhi\s+)?(?:muttafiq|ittifaq)\b"
    r"|اجماع|إجماع",
    re.IGNORECASE,
)


def validate_unreviewed_answer(answer):
    """Withhold known consensus wording; never edit a claim to make it look valid."""
    normalized = unicodedata.normalize("NFKD", answer)
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    if _CONSENSUS_WORDING.search(normalized):
        raise CitationError("unreviewed_consensus_claim")


def status_lines(result):
    """Fixed channel labels, never inferred from old percentages or dataset flags."""
    if result.get("mode") not in {"fiqh", "general", "reexpress"} or result.get("out_of_scope"):
        return []
    validation = result.get("citation_validation") or {}
    if validation.get("status") != "passed" or validation.get("scope") != CITATION_SCOPE:
        return []
    lines = ["References matched"]
    review = result.get("scholarly_review") or {}
    if review.get("status") == "not_completed" and review.get("scope") == REVIEW_SCOPE:
        lines.append("Scholarly review not completed")
    lines.append(STATUS_NOTE)
    return lines
