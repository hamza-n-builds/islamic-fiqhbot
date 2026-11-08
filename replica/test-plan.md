# Test plan: local startup

Date: 2026-11-04. Scope: actual FIQHBOT; no deployment, live AI requests, database
writes, WhatsApp sends or browser automation.

| Case | Expected | Evidence / command |
| --- | --- | --- |
| F00-H1 healthy environment | Reused without dependency installation | `python -B -m unittest discover -s tests -p test_local_startup.py -v` |
| F00-E1 missing/broken executable | Rejected by execution probe; preserved before recreation | Same startup suite |
| F00-E2 wrong Python/architecture/prefix | Rejected | Same startup suite |
| F00-E3 failed install/check | Nonzero exit, no ready marker or app launch; retry supported | Same startup suite |
| F00-E4 concurrent setup | Second setup refused; lock released on completion | Same startup suite |
| F00-E5 paths with spaces | Correct quoting, argument forwarding and exit status | Real Windows cmd subprocess tests in startup suite |
| F00-H2 actual local start | Model/data warm-up, ready health, exact frontend assets, same-origin config | `python -B tests/smoke_local_startup.py` |
| F00-E6 second local start | Reuses ready instance without a second browser/server | Same smoke script |
| F01-N1 API boundaries unchanged | Existing mocked API regression suite passes | `python -B -m unittest discover -s tests -v` |

Use the backend environment's Python. The smoke script blocks external server
network/DNS, needs local NLTK/model assets, and stops only its own server. Its
report is `replica/evidence/local-startup.json`; raw server logs are Git-ignored.
Browser layout and Gemini answer accuracy require separate future verification.

## Citation/provenance batch

| Case | Expected | Evidence |
| --- | --- | --- |
| F01-N2 invented/unprovided topic/Qur'an/hadith reference | Entire generated answer withheld; no source badges/proof | `test_citation_guard.py`, `test_citation_integrity.py` |
| F01-N3 valid corpus ID absent from prompt | Rejected | Same citation tests |
| F01-E1 missing/textless source or no source context | Excluded; no provider call when no context remains | Same citation tests |
| F01-N4 provider refusal | No general-knowledge retry | Same citation tests |
| F01-N5 altered/expired/absent receipt or edited answer/source | Rejected before rephrasing generation | Receipt/path tests and real `/ask` smoke |
| F01-H1 signed translation | Same reference set, fresh proof, source metadata retained | Real Flask route with mocked provider |
| F01-E2 translation adds/drops reference | Entire output withheld | Path tests |
| F01-H2 frontend follow-up | Prior proof forwarded; new proof persisted | `node --test tests/test_chat_receipts.cjs` (DOM fixtures) |
| F01-D1 corpus mappings/review | Report missing/textless records and review states without guesses | `python -B tests/audit_source_records.py` (currently exits 1 for open mappings) |

Final batch: 74 Python tests and four frontend VM checks passed. Six real-server
startup/HTTP checks passed with external network blocked. Source-record audit is
incomplete: two missing hadith mappings, one referenced hadith without English,
49 topics pending review and 28 unspecified. See `evidence/citation-verification.json`.
Neither stubs nor HMAC receipts verify whether a religious claim is true or
entailed by the cited text. No live provider quality evaluation was performed.

## Canonical source identity batch

| Case | Expected | Evidence |
| --- | --- | --- |
| F01-D2 legacy key collision | Resolve only the pinned row; never select the last duplicate | `test_source_records.py` |
| F01-D3 Bukhari 1395 / Muslim 11a | Return the checked existing local narration with a published URL | `test_source_identity_regressions.py` and real HTTP smoke |
| F01-D4 wrong nonempty 5590 hit | Return the canonical narration, not the goat narration under a legacy key | Source route regression |
| F01-D5 edited corpus/registry | Reject missing/changed fingerprints, duplicate canonical keys and inconsistent variants | Source registry tests |
| F01-D6 grade hold | Keep identity inspectable; exclude its text from prompt context/search | Source and citation-path tests |
| F01-D7 preservation | Both raw corpus files and fiqh wording/reviews unchanged; exactly seven reference-number edits | `evidence/source-record-verification.json` |

Four source-route regressions failed against `72384fd` before the fix. Final:
97 Python tests, four frontend VM tests and eight real startup/HTTP checks passed.
The structural reference audit now exits 0 with zero missing/textless mapped
references. The registry contains 38 primary-Arabic-text-matched identities; 37
are generation-eligible. The original legacy corpus is retained unchanged.

All 77 topics still lack completed scholarly approval. Primary identity matching
does not validate topic relevance, inferential fiqh support or a translation's
quality. Priority review observations are in `source-record-review.md`.

## Response status batch, 2026-11-08

| Case | Expected | Evidence |
| --- | --- | --- |
| F01-S1 pending/unspecified/raw approved review flag | No percentage or promoted scholarly approval; consensus null | `test_response_status.py` |
| F01-S2 general and signed rephrased answer | Same scoped citation check, explicit incomplete review, valid proof | Real pipeline and Flask-route fixtures |
| F01-S3 weak/invalid match | No generation or general fallback before source-backed acceptance | Response-status regressions |
| F01-S4 strict legacy cutoff + consensus flag | Consensus cannot make it pass | Private abstention regression |
| F01-S5 known consensus/ijma wording | Whole output withheld on fiqh/general/translation paths | Shared wording guard tests; no semantic guarantee |
| F01-S6 old signed consensus answer | Not forwarded to translation provider | Prior-receipt regression |
| F01-S7 legacy saved percentages/flags | Not rendered as accuracy, agreement or disagreement | Actual frontend functions in Node VM |
| F01-S8 status persistence | New citation/review status saved with new response proof | Same frontend suite |
| F02-S1 greeting/referral/old metadata | No `None%`, percentage or agreement footer | WhatsApp formatter tests |
| F02-S2 accepted response | Same reference/review labels and accuracy limitation as web | WhatsApp fixtures |
| F01-S9 responsive badge layout | Visible limitation, wrapping, no overflow at 390/1440px | Pending: browser access host unavailable |

Run the commands in `response-status.md`. Red-phase failures are recorded against
`a1ae80d`; final counts and limits are in `evidence/response-status-verification.json`.
Live provider behavior, semantic/scholarly support and visual browser QA are not
established by mocked fixtures or successful citation checks.

## Three-school response vertical slice, 2026-11-08

| Case | Expected | Evidence |
| --- | --- | --- |
| F01-C1 default /ask | All three ordered school sections; one organizer invocation | `test_school_comparison.py`, real loopback smoke |
| F01-C2 absent/blank position | Unavailable; excluded from provider keys; no other-school fallback | School context regressions |
| F01-C3 malformed/duplicate/extra/missing JSON key or invalid size/type | Entire structured output rejected | Strict parser/path regressions |
| F01-C4 one invalid citation/null/consensus/cross-school label | Only that section withheld; valid others kept | Section boundary regressions |
| F01-C5 weak match or no school notes | No speculative organizer call | Comparison pipeline tests |
| F01-C6 nearby secondary topic | Cannot supply missing school material | Anchoring fixture |
| F01-C7 signed translation | Same school identities and citation sets; new valid proof | Receipt and real HTTP smoke |
| F01-C8 changed answer/source or dropped citation | Pre-call tampering rejection or affected translated section withheld | Provenance tests |
| F01-C9 legacy selected history | Exact fingerprinted scope remains translatable | Legacy receipt/API regressions |
| F01-C10 direct chat + rendering | Three native disclosures; independent sources; safe text; old chats compare all | Frontend VM tests |
| F01-C11 chat switch/duplicate submit | Reply stays in original chat; one pending request per chat | Deferred-response frontend tests |
| F01-C12 colors | 12 specified new-component text pairs pass AA | Replica contrast checker and token artifact |
| F01-C13 visual/keyboard | Check real 390px/1440px layout, toggles, focus, dark/light, long/RTL text | Pending: browser host unavailable |

The loopback comparison smoke warms the actual local model/data and replaces only
the organizer with a test placeholder. It tests default comparison, signed
rephrasing and pre-provider edited-history rejection. No live provider or religious
accuracy/translation quality is evaluated. Existing startup/canonical checks and
all prior regressions remain required. See `school-comparison.md` for commands and
`evidence/school-comparison-verification.json` for exact results/preservation.

## Prototype response presentation, 2026-11-09

| Case | Expected | Evidence |
| --- | --- | --- |
| F01-U1 full comparison | Three full, safely escaped school rows; no answer dropdowns | Actual renderer/function tests |
| F01-U2 missing/withheld + stale sources | Fixed explanation remains; no stale school source group | Frontend regression |
| F01-U3 mixed language/long paragraphs | Per-paragraph direction/font; breaks and citation text retained | Frontend regression; visual wrapping pending |
| F01-U4 Copy/Listen | Exact server text; visible success/loading/reset labels and read-aloud state | Actual callback tests |
| F01-U5 sources keyboard semantics | Native disclosures; record text lazily mounted once | Native-markup/function test; actual keyboard QA pending |
| F01-U6 contrast | 44 specified intro/card/row/hover/source pairs pass AA | `evidence/response-ui-contrast.json` |
| F01-U7 actual app serving | Latest HTML/JS/CSS served byte-for-byte; startup/API safeguards intact | Nine real local startup/HTTP checks |
| F01-U8 mobile/desktop visuals | Compare 390px/1440px; dark/light; long English/RTL; sources/actions | Pending: browser access host unavailable; local synthetic preview provided |

No live generation, scholarly approval, pixel-parity score or browser rendering
claim. Six pre-implementation frontend failures and the current results are
recorded in `evidence/response-ui-verification.json`; detailed local logs/preview
are outside the application in `.audit/fiqhbot-response-ui-2026-11-09/`.

## Conversation UI, 2026-11-09

| Case | Expected | Evidence |
| --- | --- | --- |
| F01-V1 rich response | Existing paragraphs/headings/lists/bold/code render safely; no provider HTML/links | `test_response_presentation.cjs` |
| F01-V2 inline sources | Known tags become controls for that school's records only; unknown tags stay text | Same suite; malformed/hostile metadata fixtures |
| F01-V3 exact content | Rendering does not mutate section records; Copy/speech retain exact server text | Both frontend suites |
| F01-V4 source inspector | Open matching group/record; close restores focus and chat position; nonmodal fallback | Actual handler fixtures; native browser behavior pending |
| F01-V5 composer keys | Desktop Enter sends; Shift+Enter/touch/IME keep editing | Key-handler regressions; real keyboard/viewport QA pending |
| F01-V6 reading position | Do not interrupt earlier reading; follow a new reply from its start | Actual message-renderer regression |
| F01-V7 colors/serving | 42 specified pairs pass; latest assets served and existing APIs/startup intact | Contrast artifact and nine loopback HTTP checks |
| F01-V8 visual states | 390px/1440px dark/light; long/RTL; native dialog/Escape/focus; growing textarea and mobile keyboard | Pending: browser access host unavailable |

The eight new tests failed before their functions were implemented. Final counts:
26 frontend checks, 138 Python tests, nine actual local HTTP checks. See
`evidence/conversation-ui-verification.json`. The local preview under
`.audit/fiqhbot-conversation-ui-2026-11-09/preview.html` uses the actual renderer
and clearly labeled synthetic data. It is not browser QA, a live provider test,
religious guidance or a pixel-parity result. No push/deployment.

Reproduce from `backend`:

```powershell
node --test tests/test_chat_receipts.cjs tests/test_response_presentation.cjs
.\venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
.\venv\Scripts\python.exe -X utf8 -B tests/smoke_local_startup.py
.\venv\Scripts\python.exe -X utf8 -B ..\..\replica-skill-main\replica-skill-main\replica-design\contrast.py ..\replica\design\school-response-tokens.json
```
