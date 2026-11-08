# Conversation response presentation

Current specification: 2026-11-09. The owner requested a ChatGPT-like conversation
experience while retaining the brown/gold identity. This supersedes the earlier
prototype response card. The actual Flask application remains separate from the
static portfolio demo. RAG, prompts, raw structured answers and receipts stay
unchanged; the UI adds no generated summary or religious interpretation.

## Reference and tokens

The visual direction is a centered reading column, unboxed assistant content,
headings and paragraph/list hierarchy, quiet utilities and an on-demand source
inspector. The palette retains warm brown surfaces and gold accents. The earlier
owner-supplied PNG's measured colors are documented in
`../evidence/response-ui-reference.json`; it is historical palette evidence,
not the current layout target. No OpenAI logo, proprietary font or product code
is imported. No live ChatGPT screenshot parity is claimed.

Use the app's existing Inter/system font for a narrower, readable conversation
measure. The no-longer-used Montserrat request is removed from the font URL.
Preserve the app's Arabic/Urdu font utilities
on answer paragraphs and source text, not the English header/action labels.
The light theme has opaque cream surfaces and darker brown/gold text.

CSS custom properties are in `frontend/modern.css`; role values and layout are
recorded in `school-response-tokens.json`. The specified text/background pairs
pass the Replica contrast checker. The current 42 pairs cover intro bounds,
conversation/actions/references/source backgrounds, input borders and send-icon
contrast, not every color in the app shell.

## Components and behavior

- **Reading area:** centered 48rem maximum, transparent assistant content and a
  subtle right-aligned user bubble. Mobile gutters 1.125rem; body 1rem on mobile
  and 1.0625rem on desktop, line height 1.8. No nested answer scrollbar.
- **Header:** an original small outline spark and Fiqhbot label; no invented
  religious summary, selected-school emphasis or third-party brand mark.
- **School sections:** all three full answers immediately visible with 1.125rem
  headings and thin separators. A safe limited Markdown renderer handles existing
  paragraphs, bold, headings, lists and inline code; it escapes HTML and creates
  no model-provided links. Unknown references remain escaped text.
- **Unavailable/withheld:** server explanation remains visible and its state is
  printed beneath/beside the school name. No source group or passed badge is
  created for these sections, including stale saved metadata with old sources.
- **Status:** existing scoped References matched and incomplete scholarly-review
  notices, plus the accuracy limitation. No copied demo percentage or ruling badge.
- **Utilities:** quiet SVG Copy/Listen icon buttons with accessible names, native
  title hints and minimum 44px targets; a Sources pill opens the inspector.
  Copy feedback is a live status; speech retains Loading/Stop/Listen states.
  Clipboard/speech use unchanged server text, including school labels.
- **Inline references:** readable Fiqh note/Qur'an/Hadith controls bind only to
  their own school's supplied records. They open the exact source record; unknown
  references are not converted into fake proof. No pooled cross-school fallback.
- **Sources:** one native dialog per sourced response, initially closed. Desktop
  uses a right panel; up to 600px, a bottom sheet. Native focus/Escape semantics,
  explicit close control, focus/reading-position restoration and record scrolling
  are wired. A browser without `showModal` gets a nonmodal inline panel. Source
  groups retain school ownership and the shared-reference limitation. Individual
  scripture records retain native lazy disclosures and multilingual text.
- **Composer:** growing textarea, desktop Enter sends, Shift+Enter and touch Enter
  continue editing; composition/IME Enter does not submit. Maximum height 10rem.
  Sending clears its height; speech transcription also resizes it.
- **Pending/scroll/motion:** honest Preparing your answer status, no invented
  provider stages. One short reveal for new replies; saved history stays stable.
  A reader scrolling earlier messages is not pulled to the latest answer. When
  following a reply, show its start. Reduced motion disables the new effects.

Existing plain history and greeting/referral behavior remain compatible. New
structured history is rendered with this card automatically. Provider text is
escaped before limited bold/newline formatting; invalid school metadata falls
back to the safe plain-history rendering.

## Verification limits

26 actual frontend-function checks, 138 Python regressions and nine local HTTP
checks pass. See `../evidence/conversation-ui-verification.json`. These are function,
source-membership and serving checks, not religious or visual certification.

The browser access host is unavailable. Real 390px/1440px layout, font loading,
keyboard interaction, wrapping and dark/light device QA remain pending. No
same-viewport screenshot pair or image-diff/parity score is claimed. A disposable
local preview in workspace `.audit/fiqhbot-conversation-ui-2026-11-09/preview.html`
runs the actual renderer using clearly labeled synthetic records for manual review.
