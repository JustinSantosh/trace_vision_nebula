# Frontend / UX audit

Stack: static `frontend/index.html` + `assets/app.js` + `assets/styles.css`, served by FastAPI at `/`. No framework,
no build. The existing "paper and highlighter" design system (warm paper, plate-yellow highlight, status colours
reserved for decisions, light/dark tokens) was kept; new parts use its tokens only.

## Views and what changed
| View | Before | After |
|---|---|---|
| Cases | Working | Unchanged |
| Case (video + evidence) | Working | Unchanged |
| Cross-camera | Working | Unchanged |
| Performance | Colour table had hard-coded numbers and overflowed its card | Built from `/api/colour/model_info` (config method, probe file, VCoR val/test, CCTV transfer); fixed-layout table fits |
| Enforcement | Five sections stacked in one long column; parking and e-challan buttons broken or silent; no way to create a case | Tab bar (Wrong-side · Parking · E-challans · Challans raised · Audit log) with pending counts and arrow-key navigation; **Acting officer** field in the header; every action rendered from the backend state machine; inline error text; step chips showing where a case is; forms to open a parking case or draft an e-challan **from a stored vehicle** |

## Principles applied
- **No invented data on screen.** Dwell shows "not measured" instead of `0s`; fines no longer fall back to ₹1,000; OCR confidence is shown only when it came from the stored analysis, with how it was computed.
- **Honest scope.** The banner says what is simulated and lists the systems that are *not* connected (VAHAN, e-Challan, payment gateway, towing). The parking form shows when a clip cannot be assessed and why (moving camera / no zones).
- **Uncertain plates are never actionable.** The e-challan form lists only vehicles with a confident registry match.
- **Accessibility.** Tabs use `role=tab`/`tablist`/`tabpanel`, `aria-selected`, arrow keys; table rows are focusable and open with Enter; status messages use `role=status`; the officer hint is linked with `aria-describedby`.
- **Responsive.** At 390 px (device emulation) the document scroll width equals the viewport; only the tab strip scrolls internally.

## Known UI limits
- The side evidence panel scrolls on its own; long cases put "Next step" below its fold.
- Cross-camera videos can show black until the browser has buffered them (seen in headless capture).
- The upload area cannot be exercised in the browser test without a file picker; the same `/jobs` path was tested via the API with a real clip.
