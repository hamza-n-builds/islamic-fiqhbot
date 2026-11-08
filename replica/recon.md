# FIQHBOT maintenance map

Scope resumed by the owner on 2026-11-04: fix local startup first, with focused
Git commits. No deployment. The actual Flask application is separate from the
static portfolio showcase.

| Flow | Current implementation | This change |
| --- | --- | --- |
| F00 local start | Windows launcher -> Python environment -> local warm-up -> loopback HTTP server -> browser | Repair environment detection/setup; retain the existing server and UI |
| F01 web guidance | Frontend -> POST /ask -> hybrid retrieval -> source-context validation -> Gemini -> citation gate -> answer/source metadata | Citation/provenance gate implemented; semantic/scholarly validation and three-school response redesign remain pending |
| F02 WhatsApp | Signed webhook -> same answer engine -> channel reply | Unchanged; no live sends during startup verification |

F00 states: missing/wrong Python, missing/broken environment, dependency setup,
setup failure/retry, healthy reuse, knowledge-base warm-up, ready server, duplicate
launch. Browser rendering is not part of the startup runtime claim.

F01 follow-ups: message text plus server-issued proof -> proof/source-content
validation -> context-bound rephrasing -> same-citation check. Unverified history
asks the user to repeat the original question. Existing chats remain readable.

F01 source identity now resolves checked canonical registry rows, not ambiguous
legacy integer keys. All current mapped references resolve; supplementary grade
holds are omitted from generation. Original corpus/rulings/review states remain
preserved. Additional raw narrations need explicit canonical registration, while
all topic-to-source religious support still needs qualified review.

F01/F02 status presentation (2026-11-08): replace heuristic accuracy percentages
and unreviewed agreement/disagreement badges with scoped reference membership
and explicit incomplete scholarly review. Cover old saved history, new answers,
signed rephrasing, weak-match abstention, greetings/referrals, web and WhatsApp.
The source registry and religious content remain unchanged; the three-school
mobile response redesign is still a later task.

F01/F02 direct-chat vertical slice (2026-11-08): default requests retrieve three
school positions without selection. Native answer disclosures are implemented;
empty/missing/withheld sections, bounded JSON parsing, school-bound receipts,
rephrasing, old history, duplicate submits and pending chat switches are covered.
Browser visual/keyboard checks remain pending. This is a functional response/UI
change, not a full mobile visual redesign or scholarly approval.

F01 response presentation (2026-11-09): owner-provided portfolio screenshot replaces
the simple answer accordions with one warm response surface, three immediately
visible school rows, outline Listen/Copy controls and a secondary Sources panel.
Small screens stack each school label above its answer. Missing/withheld notices,
school source ownership and reference/review limits remain. RAG, source data,
receipts and the separate static portfolio are unchanged. Browser host remains
unavailable, so visual matching is implemented but not browser-verified.

F01 conversation presentation (2026-11-09): the owner's subsequent direction is
a ChatGPT-like reading experience in the same brown/gold palette. The response is
now unboxed with clear school headings and safe paragraph/list typography. Scoped
inline citation controls open a native source inspector (desktop side panel/mobile
bottom sheet). Quiet actions, visible review limits, a multiline composer, honest
pending state and one-time reply reveal replace the card presentation. Raw answer
storage, receipts, RAG and school ownership are preserved. No proprietary ChatGPT
logo/font/source was imported and no live product parity claim is made.
