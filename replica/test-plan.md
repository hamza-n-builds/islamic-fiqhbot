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
