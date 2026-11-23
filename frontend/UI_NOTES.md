# TraceVision UI notes

## Brand
- **Name:** written as the wordmark `tracevision` (lowercase, "vision" in bold).
- **Mark:** a number plate with two ink characters and one yellow cell. The yellow cell stands for a character the system won't guess.
- **Line:** *Read what's there. Mark what isn't.*
- **Palette:** ink on warm paper (`--bg #f6f5f1`, `--ink #14161a`). There is one brand colour, plate yellow (`--mark #f2c230`), used like a highlighter for what is selected and for unknown `?` characters. Green, amber and grey are kept for decisions only (match, ambiguous, no confident match). Dark mode follows the system setting.
- **Type:** system UI font, plus a monospace font for plates. Nothing is loaded from the network.
- **Plate motif:** plates always render as a small white number plate, with unknown characters filled yellow.

## Layout
Four tabs: **Cases**, **Cross-camera**, **Performance**, **Enforcement**. No sidebar, command palette, demo mode, role picker or icon buttons.

- **Cases:** a single drop area to analyse a new clip, four totals, and a table of stored cases. Click a row to open it.
- **Case** (`#case/runs/clip03` or `#case/jobs/<id>`; the old `#results/...` links still work):
  - **Left:** the vehicles. Matches come first, then the vehicles with the most readable characters.
  - **Centre:** the video with boxes and a single play button. The yellow ticks on the scrubber are the frames used for the plate. Below the video is the selected vehicle's **findings**: plate, registry, type, colour, seen, other camera when linked, **direction** when the wrong-side check ran, and **vehicle record** for a confident match.
  - **Right (evidence panel):** what the selected finding rests on. This covers per-character agreement, the frame reads (click a row to seek), plate crops, the decision rule checked in order with the deciding check highlighted, the candidates (expand one to see score parts, a character comparison and the matcher's reasons), type votes, colour votes and track stitching.
- **Cross-camera:** pick a pair, and both videos jump to the selected link. The panel shows why the two tracks were linked, the registry decision pooled from both cameras, and the synthetic vehicle record when that pooled decision is a confident match.
- **Enforcement:** the wrong-side review queue (pending items; reviewed ones fold into "Reviewed (N)"), clips checked, simulated challans raised, the audit log, and a typed registration lookup. Records and challans are synthetic and every record carries a "synthetic demo data" banner. Details: [ENFORCEMENT.md](../ENFORCEMENT.md).
- **Performance:** headline metrics. Select one to see its definition, scope and source file. Robustness bars are shown underneath.

Detail is progressive: a short value in the list, the full backing in the side panel, and long lists collapsed behind "Show all".

## Files
- `index.html`: the shell and the five views (four tabs plus the case view)
- `assets/styles.css`: tokens and components
- `assets/app.js`: routing, data loading, rendering and the video overlay
- `assets/explain.js`: pure decision-rule helpers (unchanged; tested by `node --test frontend/tests/`)

Run with `python -m tracevision.api` and open http://127.0.0.1:8000. No build step is needed. Bump `?v=` in `index.html` after editing assets so browsers fetch the new files.
