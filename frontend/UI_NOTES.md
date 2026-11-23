# TRACEVISION AI UI notes

## Design system

- Dark navy foundation with cyan, violet, and magenta used as restrained interface accents.
- Green, amber, and red are reserved for match, uncertain, and no-match states.
- Panels use subtle glass-like surfaces, thin borders, restrained gradients, and low-contrast grain.
- Interface, display, and monospace font stacks use fonts already present on the local system. There are no remote font requests or CDN dependencies. The repository contains no font assets to bundle.
- Motion is limited to scan and loading accents and is disabled for reduced-motion preferences.
- Shared patterns include cards, badges, buttons, score bars, unknown plate cells, skeletons, and accessible toast messages.

## Run

From the repository root, run `python -m tracevision.api` and open `http://127.0.0.1:8000`. FastAPI serves the page at `/` and local CSS/JS assets under `/frontend/`.

No build step or package install is required. Edit `index.html`, `assets/styles.css`, and `assets/app.js` directly.

## File map

- `index.html` - shared workspace shell, landing, upload, sample gallery, job status, results, cross-camera, reports, and insights views
- `assets/styles.css` - design tokens, responsive layout, and shared components
- `assets/app.js` - runtime overview, validation, upload, job polling, and review workspace rendering
- `backups/home.original.html` - prior inline FastAPI home-page template
- `UI_NOTES.md` - design and run notes
- `DEMO_SCRIPT.md` - three-minute stored-data judge walkthrough

## Backend change

`tracevision/api.py` serves the frontend shell and local assets, and adds `GET /api/overview`. That endpoint reads sample clips from `runs/clip*/result.json`, evaluation figures from `TRACEVISION_DATA/reports/p6_evaluation.md` and cross-camera evaluation JSON, plus upload limits and engine state.

Engine import/startup failures are caught and surfaced through `/api/overview`. `POST /jobs` returns 503 after a known startup failure. Job status responses add phase and failure-phase fields for queue, analysis, report generation, and completion. `GET /api/review` reads directional cross-camera files from `runs/crosscam/*.json`, cross-camera evaluation groups, and robustness variants from `TRACEVISION_DATA/reports/`. Overview clip records also include PDF availability for the report screen. The pipeline does not expose per-stage callbacks, so the interface reports that limitation instead of simulating detect/track/OCR progress.

## Results dashboard

The results route uses `#results/runs/clip03` for stored results and `#results/jobs/<job-id>` for completed uploads. It reads result JSON, original clip video, evidence file lists, and report links from existing FastAPI routes. The video overlay draws recorded track boxes on the synchronized frame; OCR evidence frames can be selected to seek playback.

Each vehicle shows its track, type, observed colour, detector confidence, mean fused-character OCR confidence, fused plate characters, per-frame OCR reads, ranked candidates, and recorded candidate reasons. Missing crops remain explicit placeholders. Unknown plate characters remain `?`; candidate scores are labelled as heuristic ranking scores, not probabilities. The dashboard does not display registry owner contact information.

## Cross-camera, reports, and insights

The Cross-camera screen reads all available directional pair documents through `/api/review`, loads both stored clip results and videos, and overlays their recorded track boxes. Each direction is rendered separately because stored reverse-direction decisions can differ. The center connector is solid green only for a recorded link; unlinked decisions use a dashed amber connector. Candidate scores and components are explicitly heuristic ranking values. Evaluation labels and system track IDs appear in separate sections because they are different identifiers.

The Reports screen lists clips with existing HTML reports from `/api/overview`, previews the stored report in an iframe, and exposes its existing HTML/PDF downloads when present. Insights reads headline metrics from `p6_evaluation_baseline.json` via `/api/overview`, falling back to the evaluation Markdown if the JSON is unavailable; it reads robustness variants from `p6_robustness.json` and labelled cross-camera outcomes from `crosscam_evaluation.json`. Bars are generated from runtime values; no charting package or CDN is used.

## Phase 5 polish

The command palette opens with Ctrl+K and searches workspace routes and available stored clips. Keyboard shortcuts include `?` for About and Limitations, `G` then `O` (overview), `C` (cross-camera), `I` (insights), or `R` (reports), and Esc to close native dialogs. Metric cards expose concise definitions on hover and keyboard focus. About and Limitations explains the evidence rules, local engine state, and coarse job-stage reporting.

Demo mode is explicitly simulated: choose a clip with a stored video, watch the timed stage sequence, and open the existing result. It does not upload media, call the pipeline, or create a new result. The result view carries a demo banner so the stored output and simulated progress cannot be mistaken for a live analysis. See `DEMO_SCRIPT.md` for the judge click path.
