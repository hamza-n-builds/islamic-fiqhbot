# Three-school response card

Current specification: 2026-11-09. The owner supplied
`FireShot Capture 010 - FIQHBOT - Hamza Nadeem - .png` from their own portfolio
showcase. The actual application remains separate from that static demo. This
change affects presentation; RAG, prompts, structured sections and receipts stay
unchanged. The initial native answer accordions are superseded by this design.

## Reference and tokens

The reference uses one warm brown assistant surface, a small Fiqhbot header,
three inset school rows, outline utility buttons and a secondary source panel.
Original PNG colors were sampled with the Replica PNG reader: surface `#3b2317`,
source surface `#2c180f`, border `#765334`, body `#ccbbae`, strong `#ecf0f1`, accent
`#f3af42`. See `../evidence/response-ui-reference.json` for its hash and scope.

Use Montserrat for the response card, with existing Inter/system fallback. The
existing Google Fonts declaration includes Montserrat; font delivery is not a
new runtime dependency of retrieval. Preserve the app's Arabic/Urdu font utilities
on answer paragraphs and source text, not the English header/action labels.
The light theme has opaque cream surfaces and darker brown/gold text.

CSS custom properties are in `frontend/modern.css`; role values and layout are
recorded in `school-response-tokens.json`. The 44 specified text/background pairs
pass the Replica contrast checker. This includes the earlier intro checks and
the new card/row/hover/source combinations, not every color in the app shell.

## Components and behavior

- **Response surface:** full available chat width, 1.25rem padding on desktop,
  1rem on mobile; 0.875rem radius; no fixed height or nested answer scrollbar.
- **Header:** small accent dot, Fiqhbot, School comparison. It does not invent an
  introductory religious summary or show a currently selected school.
- **School rows:** all three full answers immediately visible. Above 600px, a
  5.5rem label column and flexible answer column; up to 600px, label above answer.
  Body 1rem/1.75, labels 0.9375rem/600, paragraphs retain breaks and citations.
  Every school has equal emphasis; hovering is decorative, not a selection.
- **Unavailable/withheld:** server explanation remains visible and its state is
  printed beneath/beside the school name. No source group or passed badge is
  created for these sections, including stale saved metadata with old sources.
- **Status:** existing scoped References matched and incomplete scholarly-review
  notices, plus the accuracy limitation. No copied demo percentage or ruling badge.
- **Utilities:** outlined SVG Listen/Copy buttons, visible labels, minimum 44px
  equivalent height, focus ring. Loading/Stop and Copied/Failed states preserve
  labels. Read-aloud uses `aria-pressed` and an updated accessible action name.
  Clipboard/speech receive the unchanged server plain text, including school labels.
- **Sources:** one native `details`/`summary` beneath the utilities, initially
  closed. It contains separately named school groups; only accepted available
  sections mount their records. The topic-level shared-reference limitation stays
  visible. Individual scripture records use native disclosures with lazy text
  mounting, accessible to keyboard without a click-only div.
- **Motion:** short hover transitions and an action loading icon; reduced motion
  disables both. Answers are not progressively hidden or simulated as AI typing.

Existing plain history and greeting/referral behavior remain compatible. New
structured history is rendered with this card automatically. Provider text is
escaped before limited bold/newline formatting; invalid school metadata falls
back to the safe plain-history rendering.

## Verification limits

18 actual frontend-function checks, 138 Python regressions and nine local HTTP
checks pass. See `../evidence/response-ui-verification.json`. These are function,
source-membership and serving checks, not religious or visual certification.

The browser access host is unavailable. Real 390px/1440px layout, font loading,
keyboard interaction, wrapping and dark/light device QA remain pending. No
same-viewport screenshot pair or image-diff/parity score is claimed. A disposable
local preview in workspace `.audit/fiqhbot-response-ui-2026-11-09/preview.html`
runs the actual renderer using clearly labeled synthetic records for manual review.
