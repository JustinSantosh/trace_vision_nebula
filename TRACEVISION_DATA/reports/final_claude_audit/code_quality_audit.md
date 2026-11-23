# Code quality audit

Scope: `tracevision/` (api, parking, echallan, colour, violations, intel, pipeline entry points), `frontend/`, `tests/`.
Every fixed item is listed with its root cause and test in `execution_log.md`; this file summarises by theme.

## Fixed
**Business logic.** Approval of cancelled/disputed challans (#8), double dispute resolution (#10), towing/issuance
without a human or a reason (#12), stationarity that ignored drive-away-and-return (#15), congestion/signal waiting
treated as parking (#16), owner warning promising automatic action (#13).

**Data integrity.** Fabricated API defaults for evidence (#11); tests writing into the live ledgers (#4); non-atomic
ledger writes (#18); duplicate check outside the lock (#9).

**Crashes and silent failures.** `warning_sent` 500 when dwell is unknown (#14); four UI buttons that failed or did
nothing without telling the user (#5–#7); UI now prints the server's error text for every action.

**Integration.** Frontend/backend state names diverged (`towing_authorized` vs `towing_authorised`); the UI now
builds its actions from `/api/enforcement/meta`, so this class of drift cannot recur. Hard-coded values replaced by
data (#20, #21).

**Resource handling.** Partial uploads / orphan job folders removed on failure (#19).

## Observed, not changed (documented)
| Item | Why left |
|---|---|
| `@app.on_event("startup")` deprecation | Works on the installed FastAPI; moving to lifespan is cosmetic and risks the UI-only test harness. |
| Unused `PAGE` HTML string in `api.py` | Legacy minimal page; harmless, removing it is unrelated refactoring. |
| `job_status` reads `q.queue` without the queue's mutex | Display-only queue position; worst case a stale number. |
| JSON-file ledgers (`runs/enforcement`, `runs/audit`) | Fine for a single-process local prototype; a database is needed before multi-user use. |
| `TRACEVISION_DATA/scripts/test_*.py` are ad-hoc probes, not pytest tests | pytest only collects `tests/`; left as the team wrote them. |
| Two separate challan systems (`intel.issue_challan` "simulated challans raised" and `echallan` cases) | Both are used by existing flows (registry lookup / wrong-side review vs. case management). Merging them is an architecture change; both are clearly labelled in the UI. |
