# Security and privacy audit

This is a local, single-user prototype bound to `127.0.0.1`. That is the main control; the items below assume it
stays that way. This is not a claim that the system is secure for network deployment.

## Checked and fine
| Area | Finding |
|---|---|
| Secrets | No API keys, tokens or `.env` files in the repo or working tree. `.gitignore` excludes runs/, weights (`*.pt`), datasets |
| Path traversal | Run ids validated by regex (`clip\d+`, 12-hex job ids); image names by `^t\d+_(plate\|vehicle)_f\d+\.jpg$`; tests cover `..%2F` attempts (404). New: case ids validated (`PRK-/ECH-YYYYMMDD-XXXXXX`) |
| Upload | Extension allow-list, 500 MB cap, server-chosen filename (`upload.<ext>`); original name stored for display only, control characters stripped. Now cleaned up on failure; empty files refused |
| XSS | Frontend builds DOM with `textContent`/`createElement` (`el()` helper); no `innerHTML` with data. Viewer name is sanitised before insertion into a JS string |
| External calls | None at runtime from the UI or API. Warnings, challans, payments are local JSON records labelled simulated |
| Registration data | Registry and owner records are synthetic. A record is attached to a case vehicle only on a **confident** match (`_check_context`), and refusals are audited |

## Gaps (not fixed: they need a design decision)
| Gap | Risk if exposed beyond localhost | Recommendation |
|---|---|---|
| **No authentication or authorisation.** "Acting officer" is a typed name | Anyone who can reach the port can act as any officer | Real login (OIDC) and roles: field officer (verify), approving officer (issue/tow), adjudicator (disputes). The server already enforces *human actor + reason*; it cannot enforce *which* human |
| No CSRF protection on POST endpoints | A malicious page in the same browser could post to `127.0.0.1:8001` | Add a CSRF token or require a custom header and check `Origin` |
| Audit log and case ledgers are plain JSON files | Can be edited by anyone with file access; no tamper evidence | Append-only store with hash chaining, or a database with row history |
| No rate limiting on uploads | Disk/CPU exhaustion by repeated 500 MB uploads | Queue length cap and per-client limit |
| Dependency vulnerabilities | Not scanned (no `pip-audit` in the venv; installing tools was out of scope) | Run `pip-audit` before any deployment |
