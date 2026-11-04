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
