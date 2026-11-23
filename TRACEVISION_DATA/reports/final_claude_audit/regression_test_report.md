# Regression tests

| Suite | Before | After |
|---|---|---|
| `pytest tests` | 73 passed | **97 passed**, 0 failed, 0 skipped |
| `node --test frontend/tests/explain.test.js` | 11 passed | **11 passed** |
| `node --check frontend/assets/app.js` | ok | ok |

No existing test was removed or loosened. One existing file changed: `tests/test_parking_echallan.py` gained an
autouse fixture that points the two ledgers at `tmp_path` (its assertions are untouched). The same isolation already
existed for `intel`/`violations` tests.

## New tests (`tests/test_final_audit.py`, 24)
Parking analysis: drive-away-and-return not stationary · congestion not parking · below-limit reported · bad video
metadata → None · moving camera not assessed.
Parking workflow: towing needs warning → recheck → named human → written reason, recheck records grace period ·
unknown state name rejected · same evidence never opens two cases · warning works with unmeasured dwell (the bug
found in the live run).
E-challan: unknown evidence stays empty · invalid registration / fine rejected · cancelled cannot be approved · full
verify → approve → pay, no double payment · dispute cannot be resolved twice.
API: cancel route exists and needs a reason · malformed case ids → 404 · draft from stored evidence copies stored
attributes · unknown category / unknown vehicle refused · parking case needs stored evidence · transition needs an
officer (legacy `notes` key accepted) · parking scan is read-only · colour model info reports config.
Colour: probe loader prefers v2, falls back, handles a missing file · output always in the 12-label vocabulary.

## Live end-to-end (outside pytest)
API and browser walk-throughs of both workflows (see `browser_verification_report.md`), plus one real upload of
clip13 through `/jobs` on the running engine (see `performance_audit.md`).

## Not covered by automated tests
Detector/tracker/OCR accuracy (needs GPU-time and labelled data; covered by `python -m tracevision.evaluate`, not re-run).
