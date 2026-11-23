/* TRACEVISION AI - explainability helpers (pure functions, no DOM).
 *
 * Everything here reads values the pipeline already stored in result.json: the fused plate, the ranked candidates
 * with their match scores, and the decision thresholds recorded under result.config.match. Nothing is re-scored.
 * decisionChecks() lays the stored scores next to the stored thresholds in the same order as the decision rule in
 * tracevision/match.py (decide()), so an investigator can see which condition produced the outcome. If the stored
 * decision ever disagrees with that reading, `consistent` is false and the UI shows the stored decision unchanged.
 *
 * Loaded in the browser as window.TVExplain and in Node (tests) via require().
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.TVExplain = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function num(value) {
    if (value === null || value === undefined || value === "") return NaN;
    const n = Number(value);
    return Number.isFinite(n) ? n : NaN;
  }

  function knownCharacters(fused) {
    return typeof fused === "string" ? Array.from(fused).filter((c) => c !== "?").length : 0;
  }

  function rankedCandidates(vehicle) {
    const list = vehicle && Array.isArray(vehicle.candidates) ? vehicle.candidates.slice() : [];
    return list.sort((a, b) => num(a.rank) - num(b.rank));
  }

  /* Decision rule order (tracevision/match.py, decide()):
   *   1 no candidate                      -> no_confident_match
   *   2 readable characters < min_known   -> no_confident_match
   *   3 top match score < t_abs           -> no_confident_match
   *   4 top - second < t_margin           -> ambiguous
   *   otherwise                           -> match                                                              */
  function decisionChecks(vehicle, matchConfig) {
    const cfg = matchConfig || {};
    const minKnown = num(cfg.min_known_for_match);
    const tAbs = num(cfg.t_abs);
    const tMargin = num(cfg.t_margin);
    const fused = vehicle && vehicle.plate && typeof vehicle.plate.fused === "string" ? vehicle.plate.fused : "";
    const known = knownCharacters(fused);
    const cands = rankedCandidates(vehicle);
    const top = cands.length ? num(cands[0].match_score) : NaN;
    const second = cands.length > 1 ? num(cands[1].match_score) : NaN;
    const margin = Number.isFinite(top) && Number.isFinite(second) ? Math.round((top - second) * 10) / 10 : NaN;
    const thresholdsKnown = Number.isFinite(minKnown) && Number.isFinite(tAbs) && Number.isFinite(tMargin);

    const checks = [
      { id: "candidates", label: "Registry candidates found", observed: cands.length,
        threshold: "at least 1", pass: cands.length > 0 },
      { id: "readable", label: "Readable plate characters", observed: known,
        threshold: Number.isFinite(minKnown) ? "at least " + minKnown : "not recorded",
        pass: Number.isFinite(minKnown) ? known >= minKnown : null },
      { id: "score", label: "Top match score", observed: Number.isFinite(top) ? top : null,
        threshold: Number.isFinite(tAbs) ? "at least " + tAbs : "not recorded",
        pass: Number.isFinite(tAbs) && Number.isFinite(top) ? top >= tAbs : null },
      { id: "margin", label: "Lead over the next candidate", observed: Number.isFinite(margin) ? margin : null,
        threshold: Number.isFinite(tMargin) ? "at least " + tMargin : "not recorded",
        pass: cands.length < 2 ? true : (Number.isFinite(tMargin) && Number.isFinite(margin) ? margin >= tMargin : null),
        note: cands.length < 2 ? "only one candidate" : null },
    ];

    let derived = null;
    let decidingCheck = null;
    if (thresholdsKnown) {
      if (!checks[0].pass) { derived = "no_confident_match"; decidingCheck = "candidates"; }
      else if (!checks[1].pass) { derived = "no_confident_match"; decidingCheck = "readable"; }
      else if (!checks[2].pass) { derived = "no_confident_match"; decidingCheck = "score"; }
      else if (!checks[3].pass) { derived = "ambiguous"; decidingCheck = "margin"; }
      else derived = "match";
    }
    // Checks after the deciding one were never reached by the rule; mark them so the UI can grey them out.
    let reached = true;
    checks.forEach((check) => {
      check.reached = reached;
      if (check.id === decidingCheck) reached = false;
    });
    const stored = vehicle ? vehicle.decision : undefined;
    return {
      stored: stored,
      derived: derived,
      decidingCheck: decidingCheck,
      consistent: derived === null ? null : derived === stored,
      known: known,
      plateLength: fused.length,
      checks: checks,
    };
  }

  /* Position-by-position view of the observed plate against a registry plate. Only produced when both strings
   * have the same length; otherwise the candidate's recorded reasons are the explanation (the matcher itself uses
   * an edit distance, which this view does not try to reproduce). Look-alike substitutions are reported by the
   * matcher in its reasons; here a differing position is simply "differs". */
  function compareCharacters(observed, registration) {
    if (typeof observed !== "string" || typeof registration !== "string" || !observed || observed.length !== registration.length) {
      return null;
    }
    return Array.from(observed).map((c, i) => {
      const r = registration[i];
      return { position: i + 1, observed: c, registry: r, state: c === "?" ? "wildcard" : c === r ? "exact" : "differs" };
    });
  }

  function comparisonSummary(cells) {
    if (!Array.isArray(cells)) return null;
    const count = (state) => cells.filter((cell) => cell.state === state).length;
    return { exact: count("exact"), wildcard: count("wildcard"), differs: count("differs"), total: cells.length };
  }

  /* Score lead of the candidate at `index` (in rank order) over the next one; null for the last candidate. */
  function leadOverNext(candidates, index) {
    const list = Array.isArray(candidates) ? candidates : [];
    if (index < 0 || index >= list.length - 1) return null;
    const a = num(list[index].match_score);
    const b = num(list[index + 1].match_score);
    return Number.isFinite(a) && Number.isFinite(b) ? Math.round((a - b) * 10) / 10 : null;
  }

  /* Reasons recorded by the matcher, split into supporting and conflicting by their wording. The text itself is
   * shown unchanged; this only chooses an icon. */
  function classifyReason(reason) {
    const text = String(reason || "").toLowerCase();
    if (/conflict|differs|mismatch|does not match|veto/.test(text)) return "conflicting";
    if (/unknown|unreadable|not recorded|compatible/.test(text)) return "partial";
    return "supporting";
  }

  function frameTime(frame, fps) {
    const f = num(frame);
    const rate = num(fps) > 0 ? num(fps) : NaN;
    if (!Number.isFinite(f) || !Number.isFinite(rate)) return null;
    const seconds = f / rate;
    const minutes = Math.floor(seconds / 60);
    const rest = seconds - minutes * 60;
    return String(minutes).padStart(2, "0") + ":" + rest.toFixed(2).padStart(5, "0");
  }

  return { decisionChecks, compareCharacters, comparisonSummary, leadOverNext, classifyReason, frameTime, knownCharacters };
});
