# TRACEVISION AI Design System

**Status:** Product design direction for the investigator workspace
**Product:** Intelligent vehicle identification and investigation platform

## Brand positioning

TRACEVISION AI helps investigators and security analysts inspect vehicle evidence from CCTV and other video. It presents stored observations, plate reads, vehicle attributes, registry candidates, and cross-camera evidence in a way that supports careful decisions. It is not a general surveillance map and does not claim continuous or city-wide tracking.

The product should feel precise, trustworthy, composed, and technically capable. Its visual voice is quiet and direct: evidence is prominent, uncertainty is legible, and controls explain what they do.

## Visual direction

The workspace uses a restrained **evidence desk** direction: deep slate surfaces, soft neutral text, a single muted teal action colour, and clear semantic states. The dark palette suits long video review sessions while preserving enough contrast for labels, timestamps, and evidence notes. Screens use a steady left navigation, a readable content column, and a small number of surfaces with consistent edges.

The interface avoids decorative telemetry, fake charts, glowing borders, strong blur, and repeated placeholder thumbnails. Real footage and stored evidence belong in the review workspace. Static explanation diagrams must be identified as illustrations and must not look like recorded detections.

## Colour tokens

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0d1218` | Main canvas |
| `--bg-raised` | `#111922` | Navigation and sticky chrome |
| `--panel` | `#151e28` | Cards and evidence panels |
| `--panel-raised` | `#1b2632` | Menus, selected and elevated surfaces |
| `--panel-soft` | `#121a23` | Quiet inset regions |
| `--ink` | `#edf2f5` | Main text |
| `--muted` | `#a5b1bc` | Body support text |
| `--subtle` | `#8593a0` | Metadata and secondary labels |
| `--line` | `#2b3742` | Dividers and control borders |
| `--line-strong` | `#40505e` | Interactive borders and focus context |
| `--accent` | `#75c7bc` | Primary actions, active navigation, selected evidence |
| `--accent-strong` | `#94ddd1` | Accent text and high-priority affordances |
| `--success` | `#68c69a` | Confirmed match or completed state |
| `--warning` | `#e4b76d` | Ambiguous, partial, or review state |
| `--error` | `#e17e83` | Failure and explicit conflict |
| `--info` | `#94b5cf` | Neutral information and reference labels |

Status always includes a written label or icon as well as colour. A match, no-match, ambiguous result, unknown value, and unavailable service must remain distinguishable without colour perception. Unknown plate characters remain `?` and are never styled as guessed characters.

## Typography

- **Primary and display:** `Segoe UI Variable`, then `Segoe UI`, then `system-ui`, sans-serif. Use one family for headings and body to keep the interface calm and native on Windows.
- **Data and identifiers:** `Cascadia Code`, then `Cascadia Mono`, `Consolas`, and `ui-monospace`. Use for clip IDs, frame numbers, timestamps, and compact values only.
- **Scale:** display 34–48 px; page title 28–34 px; section title 20–24 px; card title 16–18 px; body 14–16 px; supporting text 13–14 px; metadata 12–13 px; overlines 11–12 px.
- **Line height:** 1.45–1.65 for prose; 1.1–1.25 for large values and headings.
- **Numeric data:** use tabular numerals where supported. Keep denominators, units, and source labels adjacent to a metric.

No remote font, icon, or chart requests are used. Interface icons are small inline SVGs or familiar text symbols with an accessible name.

## Layout and design tokens

- **Spacing:** 4, 8, 12, 16, 20, 24, 32, 40, 48, and 64 px. Prefer 8 px increments for page structure.
- **Radius:** 6 px for inputs and compact controls; 10 px for cards; 14 px for larger evidence and media surfaces. Avoid pill-shaped cards.
- **Borders:** one-pixel neutral borders. Use elevation sparingly; avoid blur and heavy shadows.
- **Application frame:** 232 px desktop navigation, 64 px top bar, and a content maximum width around 1,500 px. Main content uses 32–40 px gutters on large screens and 16–24 px on smaller screens.
- **Grid:** twelve-column page structure where needed; evidence views may use a flexible media column and a bounded detail rail. Summary metrics use 3–4 columns on desktop, 2 on tablet, and 1–2 on phones.
- **Control size:** 40 px minimum for primary actions and common inputs; 36 px for dense secondary actions; icon-only controls remain at least 40 px square.
- **Breakpoints:** 1,200 px (wide/standard desktop), 960 px (compact navigation and split panels), 680 px (phone layout). At narrow widths, navigation becomes a compact header and no pane may force horizontal scrolling.
- **Motion:** 120–180 ms for hover and selection feedback. No continuous scan effects or animated counters. Respect `prefers-reduced-motion`.
- **Focus:** a persistent two-pixel teal outline with offset and sufficient contrast. Do not remove browser focus without an equally visible replacement.

## Component identity

- **Navigation:** stable labels and a single understated active state; icons support text rather than replace it on desktop.
- **Buttons:** one filled teal primary action per decision area, quiet neutral secondary actions, and red only for destructive or error actions.
- **Inputs and search:** visible borders, explicit labels, clear selected values, and an empty result message. Search and filters must change displayed results.
- **Cards and lists:** use cards for a meaningful object with evidence; use compact rows for repeated investigations. Avoid identical decorative art on every row.
- **Tables:** align values, preserve units and source context, and provide row focus and overflow handling.
- **Tabs and filters:** selected state is obvious through shape, text, and colour. Never use colour alone.
- **Badges:** short, textual, and semantic: stored result, confirmed, probable, ambiguous, no confident match, unavailable.
- **Dialogs:** native modal semantics, labelled heading, visible close action, Escape behavior, and a clear primary action.
- **Tooltips:** concise definitions on hover and keyboard focus; they supplement, not replace, visible metric context.
- **Empty and error states:** describe what is missing, why it matters, and the next available action. Keep stored-result review available when live analysis is unavailable.
- **Evidence panels:** show source clip, camera, frame/time, and track identity near the evidence. Keep detector, OCR, and registry scores separate.
- **Video controls:** use native playback where possible; overlay recorded boxes at the matching frame; keep transport controls, current time, and evidence navigation discoverable.

## Screen hierarchy

### Overview

Explain the product in one short sentence and expose one primary action. Show a compact set of stored-result totals, then the evaluation with denominators and its source. A searchable, filterable investigation list follows; repeated clips use rows rather than repeated mock thumbnails. The engine state is honest and must not prevent access to stored evidence.

### Investigation results

Give the video and its recorded overlays the largest region. Keep the evidence index close to playback. The selected vehicle view groups plate, type, colour, timestamps, and decision explanation into a scannable detail panel. Let users expand frame-level OCR and candidate evidence when needed. Preserve uncertainty and recorded reasons.

### Vehicle evidence

Each vehicle item identifies its clip, track, time/frame, type, observed colour, plate read, and status when those fields exist. A missing crop is labelled as unavailable. Confidence is shown only when the backend supplies it.

### Cross-camera review

Present each camera as a separate observation with its clip ID and available timestamp. Draw a relationship only when the stored result contains it. Mark probable and plate-confirmed links differently in words and shape. State the same-scene scope alongside the view.

### Reports and insights

Keep stored report previews and source downloads obvious. Evaluation and robustness views show current source names, denominators, and caveats; charts encode actual returned data and include a textual summary.

## Interaction principles

1. Clarity over decoration.
2. Evidence over visual effects.
3. Consistency over novelty.
4. Useful whitespace over clutter.
5. Real data over fabricated numbers.
6. Functional interactions over decorative controls.
7. Keyboard access, visible focus, and readable contrast are part of the default design.
8. Preserve existing API routes, stored-result behavior, video URLs, and report generation contracts.

## Reference review

These references informed interaction and hierarchy decisions; no screen, brand, or asset is copied.

- [Mobbin — What good dashboard design looks like](https://mobbin.com/blog/what-good-dashboard-design-looks-like): treat the dashboard as a way to protect users from unfiltered data. Use a small number of priorities and put interpretation beside values.
- [21st.dev — Command palette components](https://docs.21st.dev/community/components/s/command-palette): a command palette should make search and keyboard selection legible. TRACEVISION uses its existing dependency-free native dialog rather than copying a component or adding a library.
- [Google Labs — Stitch design canvas](https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/): reviewed as a design exploration and prototyping reference. Stitch was not used to generate or export this interface.
- [Dribbble — Front analytics dashboard redesign](https://dribbble.com/shots/27358865-Front-Analytics-Dashboard-UX-Redesign): reviewed for labelled state, explicit filters, empty states, and visible keyboard focus. It is a concept reference, not a usability standard.
