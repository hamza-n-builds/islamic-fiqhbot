# Canonical source identity repair, 2026-11-04

This batch verifies narration identity/numbering. It does not approve any fiqh
ruling, decide disputed interpretations, certify translation quality or assign
an independent hadith grade. All 77 topic review statuses are unchanged: 49
pending and 28 unspecified.

## What was actually wrong

The legacy corpus's `hadith_no` field mixes numbering schemes and contains 348
duplicate key groups (702 extra rows). Constructing a dictionary from those keys
silently selected the last row. A nonempty English text was therefore not enough
to establish a correct published citation.

- Published [Bukhari 1395](https://sunnah.com/bukhari:1395) matches the existing local
  row labeled `1413`, not a missing translation. Its two topic mappings can use
  the existing owner-provided text through an explicit canonical identity.
- Published [Muslim 11a](https://sunnah.com/muslim:11a) matches the existing complete
  local row labeled `109`. The old local `11` is an Introduction entry. It was
  not filled with text from an unrelated record.
- Seven Muslim reference fields now name explicit published variants. The
  combining-prayers local reference `1664` matches published
  [Muslim 705c](https://sunnah.com/muslim:705c); it is not canonical Muslim 1664.
- Thirteen registered identities have a different published label from their
  legacy local key. This includes music, pictures and tattoos records whose old
  same-number lookup returned a different narration.

## Evidence and preservation

All 38 currently mapped hadith identities were checked against their published
Sunnah.com pages. The full Arabic text matched after deterministic Unicode NFKD
normalization, removal of the standard salutation, diacritics and punctuation.
Reference labels and in-book coordinates were also checked. Each primary URL,
normalized Arabic SHA-256 and exact local row fingerprint is recorded in
`backend/data/hadith_identity_registry.json`.

An immutable comparison snapshot of the publisher's
[hadith-api repository](https://github.com/fawazahmed0/hadith-api/tree/df57907be35291c91ad6a6691180e22ca9920784)
helped locate candidates. Primary page comparison determined the registered text
identity. Candidate search used complete text comparisons, not number equality,
topic similarity, fuzzy matching or generated paraphrases.

The original main/supplementary corpus files and all their translations remain
byte-for-byte unchanged. No external English translation was imported. Runtime
lookup and optional hadith search use registered canonical identities only;
unregistered legacy rows remain on disk and cannot become numbered citations
implicitly. An edited pinned row, missing registry, duplicate canonical key,
unmatched Arabic fingerprint or inconsistent variant fails closed.

The API and RAG engine share the same resolver. Published source URLs and
identity metadata travel with returned hadith sources. A source identity check
is explicitly kept separate from `ruling_support_review: pending`.

## Grade hold and review priorities

[Sunan Abi Dawud 2318](https://sunnah.com/abudawud:2318) is reported as
`Shadh (Al-Albani)` by the publisher. That identity remains inspectable, but its
text is excluded from generation/search until qualified review. The registry has
38 identities; 37 are generation-eligible. Eligibility does not constitute
scholarly approval or proof that a source supports a particular ruling.

These existing topic-to-source relationships need priority scholarly review.
No replacement references or revised rulings were invented in this batch.

| Topic | Observation requiring review | Published reference |
| --- | --- | --- |
| `jumuah_traveller` | The mapped narration concerns prostration during recitation; Friday/travel ruling support is unverified. | [Bukhari 1067](https://sunnah.com/bukhari:1067) |
| `touching_opposite_gender` | The mapped narration concerns tayammum; support for the stated touch ruling is unverified. | [Muslim 368d](https://sunnah.com/muslim:368d) |
| `vomiting_fasting` | The mapped narration concerns cupping while fasting; support for the vomiting rule is unverified. | [Bukhari 1938](https://sunnah.com/bukhari:1938) |
| `laughing_prayer` | The mapped narration discusses speaking/greeting during prayer; the specific laughter ruling needs review. | [Bukhari 1216](https://sunnah.com/bukhari:1216) |
| `injections_fasting` | A general fasting narration is not direct verification of modern injection classifications. | [Bukhari 1894](https://sunnah.com/bukhari:1894) |
| `zakat_salary`, `zakat_debt` | The narration establishes zakat generally; salary, nisab/haul and debt deductions need separate qualified fiqh support. | [Bukhari 1395](https://sunnah.com/bukhari:1395) |
| `pregnancy_fasting` | Publisher reports a Shadh grade; the narration is on generation hold. | [Abi Dawud 2318](https://sunnah.com/abudawud:2318) |

The remaining topics also require review; this priority list is not approval of
unlisted topics. Structural reference resolution can pass while religious
correctness, claim support and release readiness remain unapproved.
