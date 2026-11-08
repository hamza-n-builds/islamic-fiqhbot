# Response transparency, 2026-11-08

Scope: FIQHBOT's real Flask application; backend/build/test Replica phases.
Preserve the stack, datasets, source registry, existing UI identity and signed
response provenance. No deployment, push or external provider generation.

## Contract

- Accepted generated fiqh, general-reference and rephrased answers carry
  `citation_validation: {status: passed, scope: provided_reference_membership}`.
  This means only that every accepted citation resolves to supplied context.
- They also carry `scholarly_review: {status: not_completed,
  scope: answer_and_ruling_support}`. A bare dataset review flag does not establish
  independent approval of a generated answer. No approval workflow exists yet.
- Legacy confidence fields (including `confidence_reason`) and top-level
  `consensus` are null. Public fiqh-source `consensus` is also null; raw flags stay
  unchanged on disk and in the source fingerprint. Retrieval scores are not
  returned as evidence of correctness.
- Rejections/referrals/clarifications/greetings do not gain passed checks, a
  scholarly status or a receipt. Legacy mode names are retained for client
  compatibility, including `low_confidence` for fixed abstention responses.

## Behavior

All generation prompts describe dataset positions as unreviewed notes and omit
the old `Scholarly Consensus: Yes/No` and `Certainty` assertions. They instruct the
model not to claim consensus/ijma or infer disagreement from a dataset flag.
A shared conservative guard withholds whole outputs containing known consensus,
ijma/unanimity and common universal-agreement wording. The guard applies after
citation checks on all three generation paths, and to an old signed answer before
it is sent for translation. It does not delete a claim and keep the rest.

The guard is intentionally limited: definitions/negations using the same terms
can be withheld, and unrecognized paraphrases can pass. It does not verify
entailment, translation fidelity, religious correctness or scholarly consensus.
Those release requirements still need proper evaluation and qualified review.

## Retrieval abstention compatibility

Both fiqh and general-reference generation require a finite topic similarity in
0..1 clearing the existing `GENERAL_IF_BELOW` and `GENERAL_CITE_MIN` thresholds
(defaults 0.65 and 0.35, so the effective minimum is 0.65). Weak matches no longer
route into general generation at 0.35. A provider may still decline when records
exist but do not answer the question; citation checks do not establish relevance.

The old private abstention cutoff `LOW_CONFIDENCE_PCT` is retained so existing
stricter settings cannot silently be weakened. It still uses the old non-consensus
retrieval/reference-presence heuristic internally, but only returns allow/refuse.
The consensus bonus is removed. No heuristic number is presented as accuracy.
Calibration, ambiguity/margin evaluation and broader relevance evaluation remain
pending; this batch does not invent a calibrated replacement score.

## Presentation and history

Web and WhatsApp use the same fixed wording:

1. References matched
2. Scholarly review not completed
3. Matching supplied references does not verify the answer's accuracy.

The web badges are neutral, wrap on narrow screens and retain the established
theme/font. The limitation is visible text, not a hover-only tooltip. Greetings
and referrals have no confidence/disagreement badges or `None%` WhatsApp footer.
The client persists the new status alongside the signed answer proof. Old saved
percentages and consensus flags are ignored in both badges and the Sources panel;
old answer text and all chat history remain intact and have not been re-reviewed.
Optional query logging persists the new check/review fields without a false
default consensus flag.

## Verification

Reproducible commands (backend environment, from `backend` unless noted):

```powershell
.\venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
node --test tests/test_chat_receipts.cjs
.\venv\Scripts\python.exe -X utf8 -B tests/smoke_local_startup.py
.\venv\Scripts\python.exe -X utf8 -B tests/audit_source_records.py --date 2026-11-08
```

See `evidence/response-status-verification.json` for exact results and limits.
Synthetic provider fixtures test accepted and rejected response paths; they do
not evaluate live Gemini output. Browser-access availability is recorded honestly;
DOM-function VM checks are not mobile/desktop visual QA.
