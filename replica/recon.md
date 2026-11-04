# FIQHBOT maintenance map

Scope resumed by the owner on 2026-11-04: fix local startup first, with focused
Git commits. No deployment. The actual Flask application is separate from the
static portfolio showcase.

| Flow | Current implementation | This change |
| --- | --- | --- |
| F00 local start | Windows launcher -> Python environment -> local warm-up -> loopback HTTP server -> browser | Repair environment detection/setup; retain the existing server and UI |
| F01 web guidance | Frontend -> POST /ask -> hybrid retrieval -> Gemini -> answer/source metadata | Unchanged; authenticity fixes and three-school response redesign remain pending |
| F02 WhatsApp | Signed webhook -> same answer engine -> channel reply | Unchanged; no live sends during startup verification |

F00 states: missing/wrong Python, missing/broken environment, dependency setup,
setup failure/retry, healthy reuse, knowledge-base warm-up, ready server, duplicate
launch. Browser rendering is not part of the startup runtime claim.
