# Three-school response components

Keep the existing brown/orange theme and font. Native `details`/`summary` provide
independent answer disclosure controls. Three headings are always present; the
first available answer starts open. Multiple answers may remain open together.
Missing/withheld sections show their own explanation and no source panel.

Use a single column at narrow and wide widths, full chat width for comparison
messages, 1rem body text, 1.75 line height, 44px-equivalent minimum summary targets,
wrapping content and visible keyboard focus. Source disclosures are secondary
inside each answer. Copy/read-aloud use the server's school-labeled plain text.

The new component's light-theme muted/accent text is slightly darker for contrast;
existing app chrome is unchanged. Panels use an opaque theme background so small
text does not depend on gradient/alpha compositing. Check the 12 specified text
pairs with the Replica contrast tool against `school-response-tokens.json`.

States: available, unavailable, withheld, loading, API failure, old plain history,
signed translation, pending request followed by chat switch/deletion and duplicate
submit. There is no initial school selection; new questions in older chats also
request the comparison response. One request per chat can be pending at a time.

Browser host access was unavailable during this batch. Native interaction, focus,
actual wrapping/overflow, fonts and layout at 390px/1440px remain visually unverified.
DOM-function fixtures and color ratios do not replace browser QA.
