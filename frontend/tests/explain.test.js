// Run from the repository root:  node --test frontend/tests/
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const X = require("../assets/explain.js");

const CFG = { min_known_for_match: 5, t_abs: 67.5, t_margin: 4.0 };
const cand = (rank, score, reg = "AB12CD3456") => ({ rank, match_score: score, registration_number: reg, reasons: [] });

test("clear top candidate is a match and every check passes", () => {
  const r = X.decisionChecks({ decision: "match", plate: { fused: "DL3CCY1025" }, candidates: [cand(1, 100), cand(2, 86.7)] }, CFG);
  assert.equal(r.derived, "match");
  assert.equal(r.consistent, true);
  assert.ok(r.checks.every((c) => c.pass === true));
  assert.equal(r.checks.find((c) => c.id === "margin").observed, 13.3);
});

test("too few readable characters decides no confident match even with a high score", () => {
  const r = X.decisionChecks({ decision: "no_confident_match", plate: { fused: "????A?????" }, candidates: [cand(1, 99), cand(2, 10)] }, CFG);
  assert.equal(r.known, 1);
  assert.equal(r.derived, "no_confident_match");
  assert.equal(r.decidingCheck, "readable");
  assert.equal(r.checks.find((c) => c.id === "score").reached, false);
});

test("score below the threshold is no confident match", () => {
  const r = X.decisionChecks({ decision: "no_confident_match", plate: { fused: "MH12AB3456" }, candidates: [cand(1, 60.8)] }, CFG);
  assert.equal(r.decidingCheck, "score");
  assert.equal(r.consistent, true);
});

test("small lead over the runner-up is ambiguous", () => {
  const r = X.decisionChecks({ decision: "ambiguous", plate: { fused: "UP16FT9444" }, candidates: [cand(1, 80), cand(2, 77.5)] }, CFG);
  assert.equal(r.derived, "ambiguous");
  assert.equal(r.decidingCheck, "margin");
});

test("no candidates is no confident match", () => {
  const r = X.decisionChecks({ decision: "no_confident_match", plate: { fused: "HR55A?1605" }, candidates: [] }, CFG);
  assert.equal(r.decidingCheck, "candidates");
});

test("missing thresholds never invent a decision", () => {
  const r = X.decisionChecks({ decision: "match", plate: { fused: "DL3CCY1025" }, candidates: [cand(1, 100)] }, {});
  assert.equal(r.derived, null);
  assert.equal(r.consistent, null);
});

test("character comparison keeps ? as a wildcard and never fills it in", () => {
  const cells = X.compareCharacters("UP1?FT?44?", "UP16FT9444");
  assert.deepEqual(cells.map((c) => c.state), ["exact", "exact", "exact", "wildcard", "exact", "exact", "wildcard", "exact", "exact", "wildcard"]);
  assert.equal(cells[3].observed, "?");
  assert.deepEqual(X.comparisonSummary(cells), { exact: 7, wildcard: 3, differs: 0, total: 10 });
  assert.equal(X.compareCharacters("UK05D5883", "UK05O5883")[4].state, "differs");
});

test("character comparison refuses plates of different length", () => {
  assert.equal(X.compareCharacters("MH0?4?", "DL15FU7620"), null);
  assert.equal(X.compareCharacters("", "DL15FU7620"), null);
});

test("lead over next and frame timestamps", () => {
  assert.equal(X.leadOverNext([cand(1, 81.1), cand(2, 65.5)], 0), 15.6);
  assert.equal(X.leadOverNext([cand(1, 81.1)], 0), null);
  assert.equal(X.frameTime(202, 30), "00:06.73");
  assert.equal(X.frameTime(1830, 30), "01:01.00");
  assert.equal(X.frameTime(5, 0), null);
});

test("reason wording is classified without changing the text", () => {
  assert.equal(X.classifyReason("colour conflict: observed white, registry orange"), "conflicting");
  assert.equal(X.classifyReason("plate differs from UK05D6883 (edit cost 1.0)"), "conflicting");
  assert.equal(X.classifyReason("type compatible: observed SUV, registry car"), "partial");
  assert.equal(X.classifyReason("colour white matches"), "supporting");
});

// Real stored data: the explanation must reproduce every stored decision exactly.
test("decision logic reproduces the stored decision for every vehicle in runs/clip*/result.json", () => {
  const runs = path.join(__dirname, "..", "..", "runs");
  const clips = fs.readdirSync(runs).filter((d) => /^clip\d+$/.test(d) && fs.existsSync(path.join(runs, d, "result.json")));
  assert.ok(clips.length > 0, "no stored results found");
  let vehicles = 0;
  const mismatches = [];
  for (const clip of clips) {
    const result = JSON.parse(fs.readFileSync(path.join(runs, clip, "result.json"), "utf8"));
    for (const v of result.vehicles || []) {
      vehicles += 1;
      const r = X.decisionChecks(v, result.config && result.config.match);
      if (r.consistent !== true) mismatches.push(`${clip} T${v.track_id}: stored ${v.decision}, rule reading ${r.derived}`);
      // '?' is never replaced: the comparison only labels it
      for (const c of v.candidates || []) {
        const cells = X.compareCharacters(v.plate && v.plate.fused, c.registration_number);
        if (cells) cells.filter((cell) => cell.observed === "?").forEach((cell) => assert.equal(cell.state, "wildcard"));
      }
    }
  }
  assert.ok(vehicles > 100, "expected the full stored set, got " + vehicles);
  assert.deepEqual(mismatches, []);
});
