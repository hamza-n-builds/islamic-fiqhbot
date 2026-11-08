# Three-school RAG response, 2026-11-08

Baseline: `088ff16`. Scope: actual FIQHBOT backend and direct-chat vertical slice.
Replica backend/build/design/test phases; preserve Flask, retrieval/model stack,
datasets, canonical identities, styling identity and private configuration.
No push, deployment or live Gemini request was performed in this batch.

## Retrieval and organization

`/ask` without an explicit legacy school and WhatsApp request
`answer_question(..., compare_schools=True)`. Its existing greeting/meta/sensitive/
weak-match gates still run. The existing topic classifier and hybrid retriever
identify the primary topic. Only that topic can supply school notes; a nearby
secondary topic does not fill missing positions. Qur'an retrieval, canonical
hadith resolution, grade holds and private abstention cutoffs are retained.
Direct library calls retain the old flat response unless `compare_schools=True`
is passed; both served channels explicitly enable the new default comparison.

Each school receives its own ruling/explanation. Missing/blank rulings are marked
unavailable and excluded from generation. The former selected-school lookup
fallback to all other rulings is removed, including the legacy explicit-school
path. References remain topic-level/shared where that is how the dataset maps
them; no school-specific mapping or scholarly approval is invented.

One organizer invocation gets named school scopes and asks for JSON strings only
for those available keys. Null means the material cannot support an answer. The
existing provider's model fallback/retry behavior remains unchanged. Strict JSON
parsing rejects duplicate/missing/extra keys, invalid types and oversized output.
Each answer must cite its retrieved fiqh-topic note; additional references must
belong to its supplied context. Known consensus and cross-school label wording
are withheld. One invalid section is withheld without discarding valid sections.
There is no attempt to repair unsupported prose by dropping its citations.

These are structural/context-membership checks, not semantic truth tests. A model
can still misinterpret a note without introducing a new citation or school label.
Actual position fidelity, relevance and scholarly support remain unverified.

## API, provenance and channels

`mode: fiqh_comparison`, `response_schema: school_comparison_v1`, ordered
`answer_sections` with keys `hanafi`, `shafi`, `maliki` and fixed titles/statuses.
Each section has text, its cited sources and `reference_scope: topic_level_shared`.
Available sections have limited citation/review status; missing/withheld sections
have fixed localized explanations, empty sources and no passed check.
Public confidence/consensus fields remain null. An aggregated source list is
retained for existing channel/logging compatibility; topic analytics deduplicate
the same topic across three sections.

Plain `answer` is deterministically serialized with `## Hanafi`, `## Shafi'i`,
`## Maliki` headers. Model-inserted school headers are rejected. The HMAC proof
binds that exact ordered text plus a schema-namespaced digest of school identities,
statuses, per-school cited tags and source-content fingerprints. It cannot be
reused for edited school content or changed source/ruling data.

Translation verifies/parses the server's exact serialization, rebuilds the original
school-scoped context from canonical records and checks the digest before an
organizer call. Each output keeps its own original citation set. Unavailable and
withheld schools remain fixed notices. A changed citation withholds that section.
Old single-school receipts are matched only to their exact fingerprinted scope;
they are not turned into invented three-school answers during rephrasing.

WhatsApp sends the same school-labeled plain response and scoped status footer.
It has no browser accordion. No live WhatsApp send was made by this batch.

## Web presentation

Direct chat replaces the initial selection cards. The current presentation uses
an Inter reading column with three always-visible school sections, original
brown/gold colors, quiet icon actions and safe paragraph/list formatting. Inline
reference controls bind only to that section's supplied records. A native source
inspector groups records by school; desktop uses a right panel and mobile uses a
bottom sheet. Browsers without modal-dialog support receive a nonmodal inline
panel. The shared-reference limitation stays visible. Copy/read-aloud, history
and receipts retain the exact server text; no additional model call or inferred
summary is introduced. Native record disclosures retain keyboard semantics.
New history stores structured sections and the proof; old plain history remains
readable. Every new question in an old selected-school chat requests all schools.

Pending requests are scoped to their originating chat, duplicate sends in that
chat are blocked and deleted-chat replies are discarded. A reply cannot appear
in whichever chat happens to be open when it resolves. The unused direct-browser
Gemini function and commented client-credential WhatsApp block were removed;
the live chat uses the backend RAG route only.

## Verification and limits

From `backend`, with the project environment:

```powershell
.\venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
node --test tests/test_chat_receipts.cjs tests/test_response_presentation.cjs
.\venv\Scripts\python.exe -X utf8 -B tests/smoke_local_startup.py
.\venv\Scripts\python.exe -X utf8 -B tests/smoke_school_comparison.py
.\venv\Scripts\python.exe -X utf8 -B tests/audit_source_records.py --date 2026-11-08
```

`smoke_school_comparison.py` warms the real local retrieval model/datasets and uses
a test-only organizer returning placeholders after checking actual school-note
ownership. A real loopback HTTP request verifies default comparison, signed
rephrasing and pre-provider tamper rejection. It blocks external networking and
Mongo logging. It does not evaluate real Gemini answers or language quality.

The original backend batch is recorded in `evidence/school-comparison-verification.json`;
the earlier prototype UI checks are in `evidence/response-ui-verification.json`,
and current checks are in `evidence/conversation-ui-verification.json`. Browser host unavailable:
390px/1440px rendering, native keyboard interaction and real-device layout remain
pending. The current component/intro's 42 specified text/UI-color pairs pass the Replica
contrast checker; that is not a full accessibility/browser certification. All
dataset bytes/review states remain unchanged; all 77 topics still need completed
qualified review. Provider timeouts/budgets and broader readiness work are separate.
