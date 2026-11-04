# Build log

- 2026-11-04, F00: existing source checkpoint `d407bfd` preserved before changes.
  Startup recovery, read-only checks, setup serialization and regression coverage
  implemented. Fresh environment setup, local NLTK provisioning, 33 regression
  tests, read-only launcher checks and five real startup/HTTP checks passed.
  Real model/data warm-up: 11.62 seconds. No frontend, ruling-generation or
  deployment changes in this batch; no live provider-generation test performed.
