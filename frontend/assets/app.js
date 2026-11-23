"use strict";
/* TraceVision investigator UI.
 * Four views (Cases, Cross-camera, Performance, Enforcement) plus a case view. Every finding shown in the middle column has its
 * backing in the side panel: the stored reads, votes, thresholds and candidate reasons it rests on. Nothing is
 * re-scored here; values come from result.json, /api/overview and /api/review as stored. */
(() => {
  const $ = (id) => document.getElementById(id);
  const X = window.TVExplain;
  const S = {
    overview: null, review: null, route: null, result: null, files: [], cross: [], vid: null, finding: "plate",
    boxes: new Map(), req: 0, file: null, jobTimer: null, cc: { pair: null, link: null, results: {} }, perfKey: null,
    viol: null, rec: new Map(), meta: null, enfSel: null, enfManual: false, enfFiles: {},
  };

  /* ---------------------------------------------------------------- helpers */
  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    if (props) for (const [k, v] of Object.entries(props)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "text") node.textContent = v;
      else if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) node.append(kid instanceof Node ? kid : String(kid));
    return node;
  }
  const num = (v) => (v === null || v === undefined || v === "" || !Number.isFinite(Number(v)) ? NaN : Number(v));
  const pct = (v, d = 0) => (Number.isFinite(num(v)) ? (num(v) * 100).toFixed(d) + "%" : "—");
  const clock = (s) => (Number.isFinite(s) && s >= 0 ? Math.floor(s / 60) + ":" + String(Math.floor(s % 60)).padStart(2, "0") : "—");
  const cap = (s) => String(s || "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  const plural = (n, word) => n + " " + word + (n === 1 ? "" : "s");
  /* JSON call that returns the error text instead of throwing (lookups, challans, reviews). */
  async function apiCall(url, opts = {}) {
    const r = await fetch(url, Object.assign({ cache: "no-store" }, opts));
    let data = null;
    try { data = await r.json(); } catch (_) { /* empty body */ }
    return { ok: r.ok, status: r.status, data, error: data && data.detail ? data.detail : "HTTP " + r.status };
  }
  const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN");
  async function getJSON(url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(url + " returned HTTP " + r.status);
    return r.json();
  }

  function plateEl(text, large) {
    const p = el("span", { class: "plate" + (large ? " lg" : ""), "aria-label": "Plate " + text.split("").join(" ").replace(/\?/g, "unknown") });
    for (const c of text) p.append(el("i", { class: c === "?" ? "u" : null, text: c }));
    return p;
  }
  const DECISION = {
    match: ["Match", "match"], ambiguous: ["Ambiguous", "unsure"], no_confident_match: ["No confident match", "none"],
    candidate_via_probable_link: ["Candidate only", "unsure"],
  };
  const decision = (d) => DECISION[d] || [cap(d || "unknown"), "none"];
  const tag = (d) => { const [t, c] = decision(d); return el("span", { class: "tag " + c, text: t }); };

  function section(title, note, ...kids) {
    return el("section", { class: "ev-section" }, el("h4", null, title, note ? el("small", { text: note }) : null), ...kids);
  }
  function kv(rows) {
    const dl = el("dl", { class: "kv" });
    rows.filter((r) => r && r[1] !== null && r[1] !== undefined && r[1] !== "").forEach(([k, v]) => dl.append(el("dt", { text: k }), el("dd", null, v)));
    return dl;
  }
  function barRow(label, value, max = 1, shown, cls) {
    const v = num(value);
    const w = Number.isFinite(v) ? Math.max(0, Math.min(1, v / max)) * 100 : 0;
    return el("div", { class: "bar-row" }, el("span", { text: label, title: label }),
      el("div", { class: "bar " + (cls || "") }, el("i", { style: "width:" + w + "%" })), el("b", { text: shown ?? (Number.isFinite(v) ? pct(v / max) : "—") }));
  }
  function evHead(kicker, title, summary) {
    return [el("div", { class: "ev-kicker", text: kicker }), el("h3", null, title), summary ? el("p", { class: "ev-summary", text: summary }) : null];
  }
  /* Show the first `n` children of a list; a single text button reveals the rest. */
  function clamp(list, n, noun) {
    const items = Array.from(list.children);
    if (items.length <= n) return [list];
    items.slice(n).forEach((i) => { i.hidden = true; });
    const more = el("button", { class: "more", type: "button", text: "Show all " + items.length + " " + noun });
    more.addEventListener("click", () => { items.forEach((i) => { i.hidden = false; }); more.remove(); });
    return [list, more];
  }

  /* ---------------------------------------------------------------- routing */
  function route() {
    const h = location.hash.replace(/^#\/?/, "");
    const parts = h.split("/");
    const views = ["cases", "case", "crosscam", "performance", "enforcement"];
    let view = "cases";
    if ((parts[0] === "case" || parts[0] === "results") && parts.length === 3 &&
        ((parts[1] === "runs" && /^clip\d+$/.test(parts[2])) || (parts[1] === "jobs" && /^[0-9a-f]{12}$/i.test(parts[2])))) view = "case";
    else if (parts[0] === "crosscam") view = "crosscam";
    else if (parts[0] === "performance" || parts[0] === "insights") view = "performance";
    else if (parts[0] === "enforcement") view = "enforcement";
    views.forEach((v) => { $("view-" + v).hidden = v !== view; });
    document.querySelectorAll(".tabs a").forEach((a) => {
      const on = a.dataset.tab === (view === "case" ? "cases" : view);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    if (view !== "case") $("video").pause();
    if (view !== "crosscam") { $("va").pause(); $("vb").pause(); }
    document.title = { cases: "Cases", case: parts[2] || "Case", crosscam: "Cross-camera", performance: "Performance", enforcement: "Enforcement" }[view] + " · TraceVision";
    if (view === "case") openCase(parts[1], parts[2]);
    if (view === "crosscam") openCrosscam();
    if (view === "performance") openPerformance();
    if (view === "enforcement") openEnforcement();
    window.scrollTo(0, 0);
  }

  /* ---------------------------------------------------------------- overview + cases */
  async function loadOverview() {
    try {
      S.overview = await getJSON("/api/overview");
    } catch (e) {
      $("case-rows").replaceChildren(el("tr", null, el("td", { colspan: 6, class: "muted", text: "Could not reach the local service. " + e.message })));
      setEngine({ status: "error" });
      return;
    }
    setEngine(S.overview.engine || {});
    renderCases();
    if (!$("view-performance").hidden) openPerformance();
  }

  function setEngine(engine) {
    const status = engine.status || "starting";
    $("engine").dataset.state = status;
    $("engine-label").textContent = { ready: "Engine ready", starting: "Engine starting", error: "Engine unavailable", disabled: "Stored results only" }[status] || cap(status);
    const off = status !== "ready";
    $("drop").classList.toggle("is-off", off);
    $("drop").setAttribute("aria-disabled", off ? "true" : "false");
    if (!S.file) {
      $("drop-hint").textContent = status === "ready" ? "Drop a video here, or click to choose one." + limitText()
        : status === "disabled" ? (engine.message || "Live analysis is off on this machine. Stored cases are below.")
          : status === "error" ? "The analysis engine could not start. Stored cases are still available."
            : "The analysis engine is starting. This can take a minute.";
    }
    if (status === "starting") setTimeout(loadOverview, 4000);
  }
  function limitText() {
    const l = S.overview && S.overview.limits;
    if (!l) return "";
    return " " + (l.allowed_extensions || []).join(", ") + " · up to " + Math.round(l.max_bytes / 1048576) + " MB";
  }

  function renderCases() {
    const clips = S.overview.clips || [];
    const sum = (k) => clips.reduce((t, c) => t + (num(c[k]) || 0), 0);
    $("totals").replaceChildren(...[[clips.length, "cases"], [sum("vehicle_count"), "vehicles"], [sum("plates_read"), "plates read"], [sum("match_count"), "registry matches"]]
      .map(([v, l]) => el("div", null, el("b", { text: v }), el("span", { text: l }))));
    if (!clips.length) {
      $("case-rows").replaceChildren(el("tr", null, el("td", { colspan: 6, class: "muted", text: "No stored cases in runs/ yet." })));
      return;
    }
    $("case-rows").replaceChildren(...clips.map((c) => {
      const href = "#case/runs/" + c.clip_id;
      const outcome = el("div", { class: "outcome" },
        c.match_count ? el("span", { class: "tag match", text: c.match_count + " matched" }) : null,
        c.ambiguous_count ? el("span", { class: "tag unsure", text: c.ambiguous_count + " ambiguous" }) : null,
        c.no_match_count ? el("span", { class: "tag", text: c.no_match_count + " no confident match" }) : null);
      const row = el("tr", { "data-href": href },
        el("td", null, el("a", { class: "clip", href, text: c.clip_id })),
        el("td", { class: "muted", text: cap(c.camera_type) + (c.has_video ? "" : " · no video") }),
        el("td", { class: "num", text: c.vehicle_count }),
        el("td", { class: "num", text: c.plates_read ?? "—" }),
        el("td", null, outcome),
        el("td", { class: "go", text: "→" }));
      row.addEventListener("click", (e) => { if (e.target.tagName !== "A") location.hash = href; });
      return row;
    }));
  }

  /* ---------------------------------------------------------------- upload */
  function initIntake() {
    const drop = $("drop"), input = $("file");
    const ready = () => S.overview && S.overview.engine && S.overview.engine.status === "ready";
    drop.addEventListener("click", (e) => { if (e.target.id !== "start" && ready()) input.click(); });
    drop.addEventListener("keydown", (e) => { if ((e.key === "Enter" || e.key === " ") && ready()) { e.preventDefault(); input.click(); } });
    ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); if (ready()) drop.classList.add("is-over"); }));
    ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("is-over")));
    drop.addEventListener("drop", (e) => { e.preventDefault(); if (ready() && e.dataTransfer.files[0]) pick(e.dataTransfer.files[0]); });
    input.addEventListener("change", () => { if (input.files[0]) pick(input.files[0]); });
    $("start").addEventListener("click", submit);
  }
  function pick(file) {
    const l = (S.overview && S.overview.limits) || {};
    const ext = "." + file.name.split(".").pop().toLowerCase();
    if (l.allowed_extensions && !l.allowed_extensions.includes(ext)) return jobMsg("That file type isn't supported. Use " + l.allowed_extensions.join(", ") + ".", "error");
    if (l.max_bytes && file.size > l.max_bytes) return jobMsg("That file is larger than the " + Math.round(l.max_bytes / 1048576) + " MB limit.", "error");
    S.file = file;
    $("drop-title").textContent = file.name;
    $("drop-hint").textContent = (file.size / 1048576).toFixed(1) + " MB · ready to analyse";
    $("start").hidden = false;
    $("job").hidden = true;
  }
  function jobMsg(text, state, link) {
    $("job").hidden = false;
    $("job").className = "job" + (state ? " is-" + state : "");
    $("job-fill").style.width = state === "done" ? "100%" : "0";
    $("job-text").replaceChildren(text, link || "");
  }
  async function submit() {
    if (!S.file) return;
    $("start").disabled = true;
    jobMsg("Uploading " + S.file.name + "…", "running");
    const form = new FormData();
    form.append("video", S.file);
    try {
      const r = await fetch("/jobs", { method: "POST", body: form });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Upload failed (HTTP " + r.status + ").");
      const { job_id } = await r.json();
      poll(job_id, Date.now());
    } catch (e) {
      jobMsg(e.message, "error");
      $("start").disabled = false;
    }
  }
  async function poll(id, started) {
    try {
      const j = await getJSON("/jobs/" + id);
      if (j.status === "done") {
        S.file = null;
        $("start").hidden = true; $("start").disabled = false;
        $("drop-title").textContent = "Analyse a new clip";
        $("drop-hint").textContent = "Drop a video here, or click to choose one." + limitText();
        const n = j.summary && j.summary.vehicles_after_relink;
        return jobMsg("Done in " + (j.timing ? j.timing.total_s + " s" : "—") + (n !== undefined ? " · " + plural(n, "vehicle") : "") + ". ", "done",
          el("a", { href: "#case/jobs/" + id, text: "Open case →" }));
      }
      if (j.status === "error") { $("start").disabled = false; return jobMsg("Analysis failed" + (j.failed_at ? " during " + j.failed_at : "") + ": " + (j.error || "unknown error"), "error"); }
      jobMsg(j.status === "queued" ? "Queued, position " + (j.position || 1) + "…" : "Analysing · " + Math.round(j.elapsed_s || 0) + " s" + (j.phase && j.phase !== "running" ? " · " + j.phase : ""), "running");
    } catch (e) {
      jobMsg("Lost contact with the job: " + e.message + " Retrying…", "running");
    }
    if (Date.now() - started < 15 * 60 * 1000) S.jobTimer = setTimeout(() => poll(id, started), 1500);
  }

  /* ---------------------------------------------------------------- case view */
  async function openCase(kind, id) {
    const req = ++S.req;
    const base = "/data/" + kind + "/" + encodeURIComponent(id);
    $("case").hidden = true;
    $("case-state").hidden = false;
    $("case-state").className = "state-msg";
    $("case-state").textContent = "Loading " + id + "…";
    $("case-title").textContent = kind === "runs" ? id : "Uploaded clip";
    $("case-meta").textContent = "";
    $("case-links").replaceChildren();
    try {
      const [result, files, cross, viol] = await Promise.all([
        getJSON(base + "/result.json"),
        getJSON(base + "/files").catch(() => []),
        kind === "runs" ? getJSON(base + "/crosscam").catch(() => ({ links: [] })) : { links: [] },
        getJSON(base + "/violations").catch(() => null),
      ]);
      if (req !== S.req) return;
      S.route = { kind, id, base }; S.result = result; S.files = Array.isArray(files) ? files : []; S.cross = cross.links || [];
      S.viol = viol;
      renderCase();
    } catch (e) {
      if (req !== S.req) return;
      $("case-state").className = "state-msg is-error";
      $("case-state").textContent = "This case couldn't be loaded. " + e.message;
    }
  }

  const ORDER = { match: 0, ambiguous: 1, candidate_via_probable_link: 2, no_confident_match: 3 };
  function sortedVehicles() {
    const read = (v) => (v.plate && v.plate.fused ? X.knownCharacters(v.plate.fused) : 0);
    return (S.result.vehicles || []).slice().sort((a, b) => (ORDER[a.decision] ?? 9) - (ORDER[b.decision] ?? 9) || read(b) - read(a) || a.track_id - b.track_id);
  }

  function renderCase() {
    const r = S.result, v = r.video || {};
    const vehicles = sortedVehicles();
    const dur = v.frames && v.fps ? v.frames / v.fps : NaN;
    const when = r.processed_at ? new Date(r.processed_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : null;
    $("case-title").textContent = r.clip_id || S.route.id;
    $("case-meta").textContent = [cap(r.camera_type || "camera unknown"), plural(vehicles.length, "vehicle"),
      Number.isFinite(dur) ? clock(dur) + " at " + v.fps + " fps" : null, r.timing ? "analysed in " + r.timing.total_s + " s" : null, when,
      S.viol && S.viol.assessed ? "wrong-side check: " + plural(S.viol.violations.length, "suspected violation") + " in " + S.viol.checked_vehicles + " vehicles" : null].filter(Boolean).join(" · ");
    const rep = S.route.kind === "runs" ? "/runs/" + S.route.id + "/report" : "/jobs/" + S.route.id + "/report";
    $("case-links").replaceChildren(el("a", { href: rep, target: "_blank", rel: "noopener", text: "Report" }), el("a", { href: rep + ".pdf", target: "_blank", rel: "noopener", text: "PDF" }));
    $("vehicle-count").textContent = "· " + vehicles.length;

    S.boxes = new Map((r.vehicles || []).map((x) => [x.track_id, Array.isArray(x.track) ? x.track : []]));
    $("vehicle-list").replaceChildren(...vehicles.map((x) => {
      const fused = x.plate && x.plate.fused;
      const [, cls] = decision(x.decision);
      return el("li", null, el("button", { type: "button", "data-id": x.track_id, onclick: () => selectVehicle(x.track_id, true) },
        el("span", { class: "v-plate" + (fused ? "" : " none"), text: fused || "No plate read" }),
        el("i", { class: "dot " + cls, title: decision(x.decision)[0] }),
        el("span", { class: "v-sub", text: [cap(x.colour && x.colour.label), x.type && x.type.label, "T" + x.track_id].filter(Boolean).join(" · ") })));
    }));

    $("case-state").hidden = true;
    $("case").hidden = false;
    setupVideo();
    if (vehicles.length) selectVehicle(vehicles[0].track_id, false);
    else {
      $("finding-list").replaceChildren();
      $("vehicle-title").textContent = "No vehicles recorded";
      $("evidence").replaceChildren();
    }
  }

  const vehicleById = (id) => (S.result.vehicles || []).find((v) => v.track_id === id);
  function crop(vehicle, kind) {
    const re = new RegExp("^t" + vehicle.track_id + "_" + kind + "_f(\\d+)\\.jpg$");
    return S.files.filter((f) => re.test(f)).map((f) => ({ name: f, frame: Number(f.match(re)[1]), src: S.route.base + "/vehicles/" + f }));
  }

  function selectVehicle(id, seek) {
    S.vid = id;
    const v = vehicleById(id);
    document.querySelectorAll("#vehicle-list button").forEach((b) => b.setAttribute("aria-current", String(Number(b.dataset.id) === id)));
    const fused = v.plate && v.plate.fused;
    $("vehicle-title").replaceChildren(fused ? plateEl(fused) : "Vehicle T" + v.track_id);
    $("vehicle-sub").textContent = [cap(v.colour && v.colour.label), v.type && v.type.label, "track T" + v.track_id].filter(Boolean).join(" · ");
    const [t, c] = decision(v.decision);
    $("vehicle-tag").className = "tag " + c;
    $("vehicle-tag").textContent = t;
    const vc = crop(v, "vehicle")[0];
    $("vehicle-crop").hidden = !vc;
    if (vc) $("vehicle-crop").src = vc.src;

    const items = findings(v);
    if (!items.some((f) => f.id === S.finding)) S.finding = items[0].id;
    $("finding-list").replaceChildren(...items.map((f) => el("li", null,
      el("button", { class: "finding", type: "button", "data-f": f.id, onclick: () => selectFinding(f.id) },
        el("span", { class: "f-label", text: f.label }), el("span", { class: "f-value" }, f.value), el("span", { class: "f-meta", text: f.meta || "" }), el("span", { class: "f-go", text: "›" })))));
    selectFinding(S.finding);
    renderTicks(v);
    if (seek) {
      const video = $("video"), fps = num(S.result.video && S.result.video.fps) || 30;
      const best = v.plate && v.plate.per_frame_reads && v.plate.per_frame_reads[0];
      const frame = best ? best.frame : v.first_frame;
      if (video.readyState && Number.isFinite(frame)) { video.pause(); video.currentTime = frame / fps + 0.001; }
    }
    draw();
  }

  function findings(v) {
    const p = v.plate || {}, cands = X.decisionChecks ? (v.candidates || []).slice().sort((a, b) => a.rank - b.rank) : [];
    const fused = p.fused || "";
    const known = X.knownCharacters(fused);
    const top = cands[0];
    const fps = num(S.result.video && S.result.video.fps) || 30;
    const out = [
      { id: "plate", label: "Plate", value: fused ? plateEl(fused) : "Not read",
        meta: fused ? known + " of " + fused.length + " characters" : cap(p.status || "no plate found") },
      { id: "identity", label: "Registry", value: v.decision === "match" && top ? top.registration_number : decision(v.decision)[0],
        meta: top ? "score " + num(top.match_score).toFixed(1) : "no candidates" },
      { id: "type", label: "Vehicle type", value: (v.type && v.type.label) || "Unknown", meta: v.type ? pct(v.type.vote_share) + " of votes" : "" },
      { id: "colour", label: "Colour", value: cap(v.colour && v.colour.label) || "Unknown", meta: v.colour && Number.isFinite(num(v.colour.confidence)) ? "confidence " + pct(v.colour.confidence) : "" },
      { id: "seen", label: "Seen", value: clock(v.first_frame / fps) + " – " + clock(v.last_frame / fps), meta: plural(v.n_detections || 0, "detection") },
    ];
    const link = S.cross.find((l) => l.track_id === v.track_id);
    if (link) out.push({ id: "cross", label: "Other camera", value: link.other_clip + " · T" + link.other_track, meta: link.link });
    const dir = directionOf(v);
    if (dir) out.push({ id: "direction", label: "Direction", value: dir.vio ? "Wrong-side suspected" : dir.m.method === "head_on_pass" ? (dir.m.head_on ? "Oncoming (allowed here)" : "Nothing to flag") : "With the traffic flow",
      meta: dir.vio ? cap(dir.vio.review.status) + " review" : dir.m.method === "head_on_pass" ? (dir.m.head_on ? "head-on pass" : "orientation checked") : "checked in " + dir.m.zone });
    if (v.decision === "match" && top) out.push({ id: "record", label: "Vehicle record", value: "Look up " + top.registration_number, meta: "synthetic · logged" });
    return out;
  }

  function selectFinding(id) {
    S.finding = id;
    document.querySelectorAll(".finding").forEach((b) => b.setAttribute("aria-current", String(b.dataset.f === id)));
    const v = vehicleById(S.vid);
    const render = { plate: evPlate, identity: evIdentity, type: evType, colour: evColour, seen: evSeen, cross: evCross, direction: evDirection, record: evRecord }[id];
    $("evidence").replaceChildren(...render(v).flat().filter(Boolean));
    $("evidence").scrollTop = 0;
  }

  /* ---- evidence: plate */
  function evPlate(v) {
    const p = v.plate || {};
    const fps = num(S.result.video && S.result.video.fps) || 30;
    if (!p.fused) {
      return [evHead("Evidence · plate", "No plate read", "No plate text could be fused for this vehicle" + (p.status ? " (" + cap(p.status).toLowerCase() + ")" : "") + "."),
        p.plates_detected !== undefined ? section("Detector", null, kv([["Plate boxes found", p.plates_detected], ["Frames read", (p.per_frame_reads || []).length]])) : null,
        el("p", { class: "ev-note", text: "Without enough readable characters the system won't propose an identity." })];
    }
    const reads = p.per_frame_reads || [];
    const positions = p.positions || [];
    const chars = el("div", { class: "chars" }, ...positions.map((q) => el("div", { class: "char" + (q.char === "?" ? " u" : ""),
      title: q.char === "?" ? "Position " + q.pos + ": no clear winner" + (q.best_candidate ? " (best guess " + q.best_candidate + ", not shown)" : "")
        : "Position " + q.pos + ": " + pct(q.share) + " of " + q.support + " reads agree" },
      el("b", { text: q.char }), el("small", { text: q.char === "?" ? "—" : pct(q.confidence) }))));
    const table = el("table", { class: "reads" }, el("thead", null, el("tr", null, el("th", { text: "Time" }), el("th", { text: "Read" }), el("th", { class: "num", text: "Height" }), el("th", { class: "num", text: "Quality" }))));
    const body = el("tbody");
    reads.forEach((r) => body.append(el("tr", { class: "seekable", title: "Jump to frame " + r.frame, onclick: () => seekFrame(r.frame) },
      el("td", { text: X.frameTime(r.frame, fps) || r.frame }), el("td", { class: "t", text: r.text }),
      el("td", { class: "num", text: r.height_px ? r.height_px + " px" : "—" }), el("td", { class: "num", text: pct(r.quality) }))));
    table.append(body);
    const rows = Array.from(body.children);
    let more = null;
    if (rows.length > 6) {
      rows.slice(6).forEach((tr) => { tr.hidden = true; });
      more = el("button", { class: "more", type: "button", text: "Show all " + rows.length + " reads", onclick: () => { rows.forEach((tr) => { tr.hidden = false; }); more.remove(); } });
    }
    const crops = crop(v, "plate");
    return [
      evHead("Evidence · plate", plateEl(p.fused, true), "Fused from " + plural(reads.length, "frame read") + ". Each position is a vote across frames; where no character wins clearly, it stays ?."),
      section("Per character", "agreement across reads", chars),
      section("Frame reads", "click a row to see the frame", table, more),
      crops.length ? section("Plate crops", null, el("div", { class: "crops" }, ...crops.map((c) => el("img", { src: c.src, alt: "Plate crop, frame " + c.frame, title: "Frame " + c.frame, loading: "lazy" })))) : null,
      (p.warnings || []).length ? section("Warnings", null, el("ul", { class: "reasons" }, ...p.warnings.map((w) => el("li", { class: "partial", text: w })))) : null,
      el("p", { class: "ev-note", text: (p.plates_detected !== undefined ? p.plates_detected + " plate boxes detected; " : "") + "the best-quality frames were read by OCR." }),
    ];
  }

  /* ---- evidence: registry decision */
  function evIdentity(v) {
    const cfg = S.result.config && S.result.config.match;
    const cands = (v.candidates || []).slice().sort((a, b) => a.rank - b.rank);
    const [label] = decision(v.decision);
    const out = [evHead("Evidence · registry", label, v.decision_reason ? cap(v.decision_reason) + "." : null)];
    if (cfg) {
      const logic = X.decisionChecks(v, cfg);
      const list = el("ol", { class: "checks" }, ...logic.checks.map((c) => {
        const st = !c.reached ? "skip" : c.pass === true ? "pass" : c.pass === false ? "fail" : "skip";
        const shown = c.observed === null || c.observed === undefined ? "—" : c.id === "readable" ? c.observed + " of " + logic.plateLength : String(c.observed);
        return el("li", { class: st + (c.id === logic.decidingCheck ? " deciding" : "") },
          el("i", { text: st === "pass" ? "✓" : st === "fail" ? "✕" : "–" }), el("span", { text: c.label }), el("b", { text: shown }),
          el("small", { text: c.reached ? "needs " + c.threshold + (c.note ? " · " + c.note : "") : "not checked: decided earlier" }));
      }));
      out.push(section("Decision rule", "checked in order", list,
        logic.consistent === false ? el("p", { class: "ev-note", text: "The stored decision is shown unchanged; it doesn't follow from these values alone." }) : null));
    }
    if (cands.length) {
      const fused = v.plate && v.plate.fused;
      const list = el("ol", { class: "cands" }, ...cands.map((c, i) => {
        const cmp = X.compareCharacters(fused, c.registration_number);
        const sum = X.comparisonSummary(cmp);
        const lead = X.leadOverNext(cands, i);
        return el("li", null, el("details", { open: i === 0 && v.decision === "match" ? true : null },
          el("summary", null, el("span", { class: "rank", text: "#" + c.rank }), plateEl(c.registration_number || "—"), el("span", { class: "score", text: num(c.match_score).toFixed(1) })),
          el("div", { class: "body" },
            barRow("Plate", c.plate_score), barRow("Colour", c.colour_score), barRow("Type", c.type_score),
            cmp ? el("div", { class: "chars", style: "margin:10px 0" }, ...cmp.map((x) => el("div", { class: "char " + (x.state === "wildcard" ? "u" : x.state), title: "Observed " + x.observed + " · registry " + x.registry },
              el("b", { text: x.registry }), el("small", { text: x.observed })))) : null,
            sum ? el("p", { class: "ev-note", text: sum.exact + " exact · " + sum.differs + " differ · " + sum.wildcard + " unknown (top: registry, bottom: observed)" }) : null,
            el("ul", { class: "reasons" }, ...(c.reasons || []).map((r) => el("li", { class: X.classifyReason(r), text: r }))),
            lead !== null ? el("p", { class: "ev-note", text: "Leads the next candidate by " + lead + " points." }) : null)));
      }));
      out.push(section("Candidates", "top " + cands.length + " from the registry", list));
    } else out.push(section("Candidates", null, el("p", { class: "muted", text: "No registry record came close enough to rank." })));
    const w = cfg && cfg.weights;
    out.push(el("p", { class: "ev-note", text: "Match score is a ranking from 0–100" + (w ? " weighting plate " + pct(w.plate) + ", colour " + pct(w.colour) + ", type " + pct(w.type) : "") + ". It is not a probability." }));
    return out;
  }

  /* ---- evidence: type, colour, seen, cross-camera */
  function evType(v) {
    const t = v.type || {};
    return [evHead("Evidence · vehicle type", t.label || "Unknown", "Each detection votes for a type; the label is the most common vote."),
      section("Vote", null, barRow("Agreement", t.vote_share), barRow("Detector", t.detector_conf_mean, 1, pct(t.detector_conf_mean))),
      section("Source", null, kv([["Model", t.source], ["Detections", v.n_detections]])),
      el("p", { class: "ev-note", text: "Detector confidence is the mean over this vehicle's boxes. Close types (car, SUV) are often confused." })];
  }
  function evColour(v) {
    const c = v.colour || {};
    const counts = {};
    (c.per_frame || []).forEach((l) => { counts[l] = (counts[l] || 0) + 1; });
    const total = (c.per_frame || []).length;
    const rows = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([l, n]) => barRow(cap(l), n / total, 1, n + " / " + total, l === c.label ? "mark" : ""));
    return [evHead("Evidence · colour", cap(c.label) || "Unknown", "Colour is read from several vehicle crops and the most consistent label wins."),
      total ? section("Per-frame labels", null, ...rows) : null,
      section("Method", null, kv([["Method", c.note || cap(c.method)], ["Confidence", pct(c.confidence)]])),
      el("p", { class: "ev-note", text: "Colour is the least reliable attribute: lighting, shadow and dark paint shift it." })];
  }
  function evSeen(v) {
    const fps = num(S.result.video && S.result.video.fps) || 30;
    const merged = (v.merged_track_ids || []).filter((t) => t !== v.track_id);
    const crops = crop(v, "vehicle");
    return [evHead("Evidence · track", clock(v.first_frame / fps) + " – " + clock(v.last_frame / fps), "Where this vehicle appears in the clip, from the tracker."),
      section("Track", null, kv([["First frame", v.first_frame], ["Last frame", v.last_frame], ["Detections", v.n_detections],
        ["Stitched from", merged.length ? ["T" + v.track_id, ...merged.map((t) => "T" + t)].join(" + ") : null]])),
      merged.length ? el("p", { class: "ev-note", text: "The tracker lost and re-found this vehicle; the pieces were re-linked by position and plate." }) : null,
      crops.length ? section("Vehicle crops", null, el("div", { class: "crops" }, ...crops.map((c) => el("img", { src: c.src, alt: "Vehicle crop, frame " + c.frame, style: "height:64px", loading: "lazy" })))) : null,
      el("button", { class: "more", type: "button", text: "Jump to first appearance", onclick: () => seekFrame(v.first_frame) })];
  }
  function evCross(v) {
    const l = S.cross.find((x) => x.track_id === v.track_id);
    const f = l.final || {};
    return [evHead("Evidence · other camera", l.other_clip + " · T" + l.other_track, cap(l.link) + ", link score " + l.link_score + "."),
      section("Why they're linked", null, el("ul", { class: "reasons" }, ...(l.evidence || []).map((r) => el("li", { class: X.classifyReason(r), text: r })))),
      section("Pooled from both cameras", null, kv([["Plate", f.plate ? plateEl(f.plate) : null], ["Reads pooled", f.reads_pooled], ["Decision", f.decision ? tag(f.decision) : null], ["Match score", f.match_score]])),
      el("a", { class: "more", href: "#crosscam", text: "Open cross-camera view" })];
  }

  /* ---- evidence: wrong-side driving */
  function directionOf(v) {
    if (!S.viol || !S.viol.assessed) return null;
    const m = (S.viol.per_vehicle || {})[String(v.track_id)];
    if (!m) return null;
    return { m, vio: (S.viol.violations || []).find((x) => x.track_id === v.track_id) };
  }
  const deg = (u) => Math.round(Math.acos(Math.max(-1, Math.min(1, u))) * 180 / Math.PI);
  function arrow(dirv, cls) {
    const a = Math.atan2(dirv[1], dirv[0]) * 180 / Math.PI;
    return el("span", { class: "dir-arrow " + (cls || ""), style: "transform:rotate(" + a + "deg)", "aria-hidden": "true", text: "→" });
  }
  function dirs(m, bad) {
    return el("div", { class: "dirs" },
      el("div", null, arrow(m.allowed_direction), el("small", { text: "permitted" })),
      el("div", null, arrow(m.observed_direction, bad ? "bad" : "good"), el("small", { text: "observed" })));
  }
  const reviewTag = (st) => el("span", { class: "tag " + (st === "confirmed" ? "match" : st === "pending" ? "unsure" : ""), text: cap(st) });
  /* Head-on pass (moving camera): what the orientation check measured. */
  function headOnNodes(m, fps) {
    if (!m.head_on) return [kv([["Crops checked", m.samples], ["Result", "no head-on pass (front then rear not both seen)"]])];
    return [el("div", { class: "dirs" },
        el("div", null, el("span", { class: "dir-arrow bad", "aria-hidden": "true", text: "↓" }), el("small", { text: "front first" })),
        el("div", null, el("span", { class: "dir-arrow", "aria-hidden": "true", text: "↑" }), el("small", { text: "then rear" }))),
      kv([["Front seen", clock(m.front_frames[0] / fps) + " – " + clock(m.front_frames[m.front_frames.length - 1] / fps) + " (" + m.front_frames.length + " crops)"],
        ["Rear seen", clock(m.rear_frames[0] / fps) + " – " + clock(m.rear_frames[m.rear_frames.length - 1] / fps) + " (" + m.rear_frames.length + " crops)"],
        ["Grew while facing camera", m.growth + "×"], ["Front score (median)", pct(m.p_front_median)], ["Rear score (median)", pct(m.p_rear_median)]])];
  }
  function evDirection(v) {
    const { m, vio } = directionOf(v);
    const fps = num(S.result.video && S.result.video.fps) || 30;
    if (m.method === "head_on_pass") {
      const out = [evHead("Evidence · direction", vio ? "Wrong-side driving suspected" : m.head_on ? "Passed the camera head-on" : "No head-on pass",
        vio ? "It came towards the camera facing it, then went past (its rear seen after). On this road that is against the flow. It stays a suspicion until reviewed."
          : m.head_on ? "Front seen first, then rear: normal oncoming traffic on a two-way road." : "Front and rear were not both seen in that order, so nothing to flag.")];
      out.push(section("Measured", "moving camera · vehicle orientation", ...headOnNodes(m, fps)));
      out.push(section("Rule", null, el("ul", { class: "reasons" },
        el("li", { class: "partial", text: "CLIP scores each crop: front (headlights, grille) vs rear (red tail lights, boot)" }),
        el("li", { class: "partial", text: "flagged when the front is seen clearly while it grows at least 2×, then the rear" }),
        el("li", { class: S.viol.layout === "one_way" ? "conflicting" : "partial", text: S.viol.layout_note || "" }))));
      if (vio) {
        out.push(section("Review", null, kv([["Status", reviewTag(vio.review.status)], ["Registration", vio.registration_number || "no confident match"]])),
          el("a", { class: "more", href: "#enforcement", text: "Open the review queue" }),
          el("button", { class: "more", type: "button", text: "Jump to where it faces the camera", onclick: () => seekFrame(m.front_frames[Math.floor(m.front_frames.length / 2)]) }),
          el("button", { class: "more", type: "button", text: "Jump to where it has passed", onclick: () => seekFrame(m.rear_frames[Math.floor(m.rear_frames.length / 2)]) }));
      }
      if (S.viol.camera_description) out.push(el("p", { class: "ev-note", text: S.viol.camera_description }));
      return out;
    }
    const st = S.viol.stabilisation;
    const out = [evHead("Evidence · direction", vio ? "Wrong-side driving suspected" : "Moving with the traffic flow",
      vio ? "Inside the " + m.zone + ", this vehicle moves against the permitted direction. It stays a suspicion until reviewed."
        : "Inside the " + m.zone + ", this vehicle moves the permitted way.")];
    out.push(section("Measured", "in the camera's reference view", dirs(m, vio),
      kv([["Angle off the permitted direction", deg(m.cos_to_allowed) + "°"], ["Steps moving against the flow", pct(m.against_flow_share)],
        ["Distance covered", pct(m.displacement_frac) + " of frame height"], ["Points in zone", m.points],
        ["Time", clock(m.first_frame / fps) + " – " + clock(m.last_frame / fps)]])));
    out.push(section("Rule", null, el("ul", { class: "reasons" },
      el("li", { class: m.cos_to_allowed <= -0.5 ? "conflicting" : "supporting", text: "flagged only when more than 120° off the permitted direction" }),
      el("li", { class: m.against_flow_share >= 0.7 ? "conflicting" : "supporting", text: "and only when at least 70% of short steps go against the flow" }),
      st ? el("li", { class: "partial", text: "camera pan removed first (up to " + st.max_pan_px + " px; " + st.frames_usable + " of " + st.frames_sampled + " sampled frames usable)" }) : null)));
    if (vio) {
      out.push(section("Review", null, kv([["Status", reviewTag(vio.review.status)],
        ["Registration", vio.registration_number || "no confident match"]])),
        el("a", { class: "more", href: "#enforcement", text: "Open the review queue" }),
        el("button", { class: "more", type: "button", text: "Jump to the evidence frame", onclick: () => seekFrame(vio.evidence_frames[1]) }));
    }
    if (S.viol.camera_description) out.push(el("p", { class: "ev-note", text: S.viol.camera_description }));
    return out;
  }

  /* ---- evidence: vehicle record (synthetic, logged) */
  function lookupForm(onGo, label) {
    const reason = el("select", { class: "field", "aria-label": "Reason for this lookup (optional)" },
      el("option", { value: "", text: "Reason (optional, logged)" }),
      ...((S.meta && S.meta.reasons) || []).map((r) => el("option", { value: r, text: r })));
    const msg = el("p", { class: "ev-note", role: "status" });
    const go = el("button", { class: "btn", type: "button", text: label || "Look up", onclick: () => onGo(reason.value, msg) });
    return el("div", { class: "lookup" }, reason, go, msg);
  }
  /* Fetch and show the full record for `reg` into `holder`, with the issue-challan form. `context` ties it to a case vehicle. */
  async function loadRecord(reg, context, holder, reason, msg) {
    if (msg) msg.textContent = "Looking up…";
    const q = new URLSearchParams({ reason: reason || "" });
    if (context) q.set("context", context);
    const r = await apiCall("/api/intel/" + encodeURIComponent(reg) + "?" + q);
    if (!r.ok) { if (msg) msg.textContent = r.error; else holder.replaceChildren(el("p", { class: "ev-note", text: r.error })); return null; }
    S.rec.set(reg, r.data);
    holder.replaceChildren(...recordNodes(r.data, context, () => loadRecord(reg, context, holder, "Refresh after change")));
    return r.data;
  }
  /* Record holder for `reg`: the cached record, or the lookup form. `context` (runs/clip03:T1 or "") ties it to a case vehicle. */
  function recordHolder(reg, context, note) {
    const holder = el("div");
    if (S.rec.has(reg)) holder.replaceChildren(...recordNodes(S.rec.get(reg), context, () => loadRecord(reg, context, holder, "Refresh after change")));
    else holder.replaceChildren(lookupForm((reason, msg) => loadRecord(reg, context, holder, reason, msg), "Show record and challans"),
      el("p", { class: "ev-note", text: note }));
    return holder;
  }
  function evRecord(v) {
    const reg = v.candidates.slice().sort((a, b) => a.rank - b.rank)[0].registration_number;
    const context = S.route.kind + "/" + S.route.id + ":T" + v.track_id;
    const head = evHead("Vehicle record · synthetic", plateEl(reg, true), "Attached because this vehicle is a confident registry match.");
    return [head, recordHolder(reg, context, "Each lookup is written to the audit log with this case.")];
  }
  /* Cross-camera: a record is attached only when the plate pooled from both cameras gives a confident registry match.
   * The lookup is tied to whichever camera's own vehicle is also a confident match to that record, so the server can check it. */
  function ccRecord(l) {
    const f = l.final;
    if (!f || f.decision !== "match" || !f.registry_top1) {
      return section("Registry history and e-challans", null, el("p", { class: "muted", text: "Not shown: the pooled plate isn't a confident registry match, so no record is attached to this vehicle." }));
    }
    const reg = f.registry_top1;
    const own = (r, side) => {
      const veh = r && (r.vehicles || []).find((x) => x.track_id === l[side].track_id);
      const top = veh && (veh.candidates || []).slice().sort((a, b) => a.rank - b.rank)[0];
      return veh && veh.decision === "match" && top && top.registration_number === reg ? "runs/" + l[side].clip_id + ":T" + l[side].track_id : null;
    };
    const context = own(S.cc.ra, "a") || own(S.cc.rb, "b") || "";
    return el("section", { class: "ev-section" },
      el("div", { class: "ev-kicker", text: "Vehicle record · synthetic" }),
      el("h3", null, plateEl(reg, true)),
      el("p", { class: "ev-summary", text: "Registration details, compliance and e-challan history for the record both cameras matched. You can issue a simulated challan from here." }),
      recordHolder(reg, context, "Each lookup is written to the audit log" + (context ? " with " + context.replace("runs/", "") + "." : " as a cross-camera lookup.")));
  }
  const COMPLIANCE = { valid: ["Valid", "match"], expiring: ["Expiring", "unsure"], expired: ["Expired", "fail"], unknown: ["Unknown", ""] };
  function compl(c) {
    const [t, cls] = COMPLIANCE[c.state] || COMPLIANCE.unknown;
    return el("span", null, el("span", { class: "tag " + cls, text: t }), " ", el("small", { class: "muted", text: c.until || "" }));
  }
  const statusTag = (s) => el("span", { class: "tag " + (s === "Paid" ? "match" : s === "Pending" ? "unsure" : ""), text: s });
  async function cancelChallan(id, after) {
    const r = await apiCall("/api/challans/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ challan_id: id }) });
    if (r.ok && after) await after();
    return r;
  }
  function issueForm(rec, context, after) {
    const fines = (S.meta && S.meta.violations) || {};
    const vio = el("select", { class: "field", "aria-label": "Violation" }, el("option", { value: "", text: "Choose a violation…" }),
      ...Object.entries(fines).map(([k, f]) => el("option", { value: k, text: k + " · " + inr(f) })));
    const fine = el("input", { class: "field", type: "number", min: 1, max: 100000, step: 1, placeholder: "Fine (₹)", "aria-label": "Fine in rupees" });
    vio.addEventListener("change", () => { fine.value = fines[vio.value] || ""; });
    const where = el("input", { class: "field", maxlength: 120, placeholder: "Location", "aria-label": "Location",
      value: context ? context.split(":")[0].split("/")[1] + " (camera)" : "" });
    const note = el("input", { class: "field", maxlength: 300, placeholder: "Note (optional)", "aria-label": "Note" });
    const msg = el("p", { class: "ev-note", role: "status" });
    const go = el("button", { class: "btn", type: "button", text: "Issue challan", onclick: async () => {
      if (!vio.value) { msg.textContent = "Choose a violation."; vio.focus(); return; }
      go.disabled = true;
      const r = await apiCall("/api/challans", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ registration_number: rec.vehicle.registration_number, violation: vio.value, fine_inr: fine.value, location: where.value, note: note.value, context }) });
      go.disabled = false;
      if (!r.ok) { msg.textContent = r.error; return; }
      await after();
    } });
    return section("Issue a challan", "simulated · never sent anywhere",
      el("div", { class: "lookup", style: "margin-top:0" }, vio, el("div", { class: "two" }, fine, where), note, go, msg));
  }
  function recordNodes(rec, context, after) {
    const v = rec.vehicle, sum = rec.challan_summary;
    const out = [el("p", { class: "demo-banner small", text: rec.notice })];
    out.push(el("div", { class: "rec-stats" },
      el("div", null, el("b", { text: sum.pending }), el("span", { text: "pending challans" })),
      el("div", null, el("b", { text: inr(sum.pending_amount_inr) }), el("span", { text: "outstanding" })),
      el("div", null, el("b", { text: sum.total }), el("span", { text: "on record" }))));
    out.push(section("Registered owner", null,
      kv([["Name", rec.owner.name], ["Owner", rec.owner.type + (rec.owner.serial ? " · owner no. " + rec.owner.serial : "")]])));
    out.push(section("Vehicle", null, kv([["Make / model", [v.manufacturer, v.model].filter(Boolean).join(" ")], ["Model year", v.model_year],
      ["Type", v.vehicle_type], ["Class", v.vehicle_class], ["Fuel", v.fuel_type], ["Colour", cap(v.colour)], ["RTO", v.rto], ["Registered", v.registration_date]])));
    out.push(section("Compliance", "checked against today", kv([["Registration / fitness", compl(rec.compliance.registration)],
      ["Insurance", compl(rec.compliance.insurance)], ["PUC", compl(rec.compliance.puc)]])));
    const t = el("table", { class: "reads challans" }, el("thead", null, el("tr", null, el("th", { text: "Violation" }), el("th", { class: "num", text: "Fine" }), el("th", { text: "Status" }))));
    const body = el("tbody");
    rec.challans.forEach((c) => {
      const sim = c.source === "simulated_issued";
      body.append(el("tr", { title: c.challan_id + " · " + c.issuing_authority + (c.note ? " · " + c.note : "") },
        el("td", null, c.violation, sim ? el("span", { class: "tag plain sim", text: "issued here" }) : null,
          el("small", { class: "sub", text: c.date.replace("T", " ").slice(0, 16) + " · " + c.location + " · " + c.challan_id })),
        el("td", { class: "num", text: inr(c.fine_inr) }),
        el("td", null, statusTag(c.status), sim && after ? el("button", { class: "more", type: "button", text: "Cancel", title: "Cancel this simulated challan",
          onclick: () => cancelChallan(c.challan_id, after) }) : null)));
    });
    t.append(body);
    out.push(section("e-Challan history", rec.challans.length ? "newest first" : null, rec.challans.length ? t : el("p", { class: "muted", text: "No challans on record." })));
    if (after) out.push(issueForm(rec, context, after));
    return out;
  }

  /* ---------------------------------------------------------------- enforcement */
  const pad = (text) => el("p", { class: "muted", style: "padding:14px 16px", text });
  async function openEnforcement() {
    $("ws-list").replaceChildren(el("li", { class: "muted", style: "padding:12px", text: "Loading…" }));
    let data;
    try { data = await getJSON("/api/violations"); } catch (e) {
      $("ws-list").replaceChildren(el("li", { class: "muted", style: "padding:12px", text: "Couldn't load violations. " + e.message })); return;
    }
    const as = data.assessed_clips || [];
    $("ws-scope").textContent = "· " + plural(as.length, "clip") + " · " + as.reduce((t, c) => t + c.checked_vehicles, 0) + " vehicles checked";
    const vs = data.violations || [];
    $("ws-count").textContent = vs.filter((x) => x.review.status === "pending").length || "";
    await Promise.all([...new Set(vs.map((x) => x.run))].filter((r) => !S.enfFiles[r]).map(async (r) => {
      S.enfFiles[r] = await getJSON("/data/" + r + "/files").catch(() => []);
    }));
    /* Pending items form the queue; reviewed ones leave it and fold into a "Reviewed" group (still reachable to reset). */
    const pending = vs.filter((x) => x.review.status === "pending");
    const reviewed = vs.filter((x) => x.review.status !== "pending");
    S.enfPending = pending.map((x) => x.violation_id);
    const row = (x) => el("li", { class: x.review.status === "pending" ? null : "reviewed-row" }, el("button", { class: "metric", type: "button", "data-k": x.violation_id, onclick: () => selectViolation(x) },
      el("b", { class: x.registration_number ? "mono-sm" : "none", text: x.registration_number || "No plate match" }),
      el("span", null, x.label + " · " + x.clip_id + " T" + x.track_id, el("small", { text: [x.severity && x.severity !== "not_a_violation" ? "Severity: " + cap(x.severity) : null, cap(x.colour), x.vehicle_type, clock(x.time_s[0]) + "–" + clock(x.time_s[1])].filter(Boolean).join(" · ") })),
      reviewTag(x.review.status)));
    const rows = pending.map(row);
    if (vs.length && !pending.length) rows.push(el("li", { class: "muted", style: "padding:12px 14px", text: "All caught up: every suspected violation has been reviewed." }));
    if (reviewed.length) {
      const toggle = el("button", { class: "group-toggle", type: "button", "aria-expanded": String(!!S.enfShowReviewed),
        onclick: () => { S.enfShowReviewed = !S.enfShowReviewed; openEnforcement(); } },
        (S.enfShowReviewed ? "▾ " : "▸ ") + "Reviewed (" + reviewed.length + ")");
      rows.push(el("li", null, toggle));
      if (S.enfShowReviewed) rows.push(...reviewed.map(row));
    }
    const fixedCams = as.filter((c) => c.method === "zone_direction");
    const moving = as.filter((c) => c.method === "head_on_pass");
    const checked = fixedCams.map((c) => el("li", null, el("a", { class: "metric", href: "#case/" + c.run },
      el("b", { text: String(c.flagged) }),
      el("span", null, c.clip_id + " · fixed camera", el("small", { text: c.checked_vehicles + " vehicles checked in the zone" + (c.stabilisation ? " · camera pan up to " + c.stabilisation.max_pan_px + " px removed" : "") })),
      el("span", { class: "f-go", text: "›" }))));
    if (moving.length) checked.push(el("li", null, el("div", { class: "metric" },
      el("b", { text: String(moving.reduce((t, c) => t + c.flagged, 0)) }),
      el("span", null, plural(moving.length, "moving-camera clip"), el("small", { text: moving.reduce((t, c) => t + c.checked_vehicles, 0) + " cars checked for a head-on pass (front then rear)" })),
      el("span"))));
    $("ws-list").replaceChildren(...rows, ...checked, el("li", { class: "muted small", style: "padding:12px",
      text: vs.length ? "Confirm or reject each suspected violation. A confirmed one on a vehicle with a confident plate match raises a simulated challan."
        : "No wrong-side driving found. Fixed cameras: direction in a hand-drawn zone. Moving cameras: a car seen front first, then rear." }));
    const issued = (data.issued_challans || []).slice().sort((a, b) => (b.date || "").localeCompare(a.date || ""));
    $("issued").replaceChildren(issued.length ? el("table", { class: "cases" },
      el("thead", null, el("tr", null, ...["Challan", "Registration", "Violation", "Fine", "Issued", ""].map((h) => el("th", { text: h })))),
      el("tbody", null, ...issued.map((c) => el("tr", null, el("td", { class: "clip", text: c.challan_id }), el("td", null, plateEl(c.registration_number)),
        el("td", { text: c.violation }), el("td", { class: "num", text: inr(c.fine_inr) }),
        el("td", { class: "muted", text: (c.date || "").replace("T", " ") + (c.context ? " · " + c.context : "") }),
        el("td", null, el("button", { class: "more", type: "button", text: "Cancel", onclick: () => cancelChallan(c.challan_id, async () => { S.rec.clear(); await openEnforcement(); }) }))))))
      : pad("None yet. Look up a vehicle and use “Issue a challan”, or confirm a suspected violation on a matched vehicle."));
    renderParking();
    renderEChallans();
    renderAudit();
    const keep = vs.find((x) => x.violation_id === S.enfSel);
    if (keep) selectViolation(keep); else if (!S.enfManual) manualLookup();
  }
  /* One-off note about the review just made, shown at the top of whatever the panel shows next. */
  function flashNode() {
    if (!S.enfFlash) return null;
    const n = el("p", { class: "flash", role: "status", text: S.enfFlash });
    S.enfFlash = null;
    return n;
  }
  /* ---------------------------------------------------------------- parking + e-challan workflows
   * Actions are rendered from the backend state machine (/api/enforcement/meta), so the UI can only offer moves the
   * server will accept. Every action is attributed to the acting officer typed in the page header and the server's
   * error text is shown in place (nothing fails silently). All of it is simulated and stays on this machine. */
  const PARK_LABEL = {
    detected: "Detected", pending_verification: "Verifying", verified_violation: "Verified violation",
    owner_notification_pending: "Warning prepared", warning_sent: "Owner warned", vehicle_moved: "Vehicle moved",
    violation_unresolved: "Unresolved after recheck", echallan_pending: "E-challan pending", echallan_issued: "E-challan issued",
    towing_authorised: "Towing authorised", closed: "Closed", disputed: "Disputed", towed: "Towed",
  };
  const PARK_ACTION = {
    pending_verification: "Start verification", verified_violation: "Confirm violation from evidence",
    owner_notification_pending: "Prepare owner warning", warning_sent: "Send warning (simulated)",
    vehicle_moved: "Recheck: vehicle has moved", violation_unresolved: "Recheck: still there",
    echallan_pending: "Proceed to e-challan", echallan_issued: "Record e-challan issued", towing_authorised: "Authorise towing",
    towed: "Record vehicle towed", disputed: "Record dispute", closed: "Close case",
  };
  const PARK_TONE = (st) => ({ vehicle_moved: "match", closed: "match", warning_sent: "unsure", owner_notification_pending: "unsure",
    violation_unresolved: "fail", towing_authorised: "fail", towed: "fail", disputed: "fail", echallan_pending: "unsure" })[st] || "";
  const ECH_LABEL = { draft: "Draft", pending_review: "Awaiting approval", approved: "Approved", issued: "Issued (simulated)",
    paid: "Paid (simulated)", disputed: "Disputed", cancelled: "Cancelled" };
  const ECH_TONE = (st) => ({ issued: "match", paid: "match", draft: "unsure", pending_review: "unsure", disputed: "fail" })[st] || "";
  const JSONH = { "Content-Type": "application/json" };
  const post = (url, body) => apiCall(url, { method: "POST", headers: JSONH, body: JSON.stringify(body || {}) });

  function officerName() {
    const v = ($("officer") && $("officer").value || "").trim();
    return v;
  }
  function initOfficer() {
    const f = $("officer");
    if (!f) return;
    try { f.value = localStorage.getItem("tv.officer") || ""; } catch (_) { /* storage unavailable */ }
    f.addEventListener("input", () => { try { localStorage.setItem("tv.officer", f.value.trim()); } catch (_) { /* ignore */ } });
  }
  async function enfMeta() {
    if (!S.enfMeta) S.enfMeta = await getJSON("/api/enforcement/meta").catch(() => null);
    return S.enfMeta;
  }
  /* Run an action: needs an officer name, shows the server's answer in `msg`, then refreshes the view and reopens `reopen`. */
  async function runAction(msg, call, reopen) {
    if (!officerName()) { msg.textContent = "Type your name in “Acting officer” at the top of the page first. Every action is recorded against it."; $("officer").focus(); return; }
    msg.textContent = "Working…";
    const r = await call();
    if (!r.ok) { msg.textContent = r.error; return; }
    S.enfFlash = r.data && r.data.duplicate_of_open_case ? "An open case already exists for this vehicle; showing it." : null;
    await openEnforcement();
    if (reopen && r.data) reopen(r.data);
  }

  function setEnfTab(tab) {
    S.enfTab = tab;
    document.querySelectorAll("#enf-tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
    document.querySelectorAll("#view-enforcement [data-pane]").forEach((p) => { p.hidden = p.dataset.pane !== tab; });
  }
  function initEnfTabs() {
    const bar = $("enf-tabs");
    if (!bar) return;
    bar.addEventListener("click", (e) => { const b = e.target.closest("button[data-tab]"); if (b) setEnfTab(b.dataset.tab); });
    bar.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const bs = [...bar.querySelectorAll("button")]; const i = bs.indexOf(document.activeElement);
      if (i < 0) return;
      const n = bs[(i + (e.key === "ArrowRight" ? 1 : bs.length - 1)) % bs.length]; n.focus(); setEnfTab(n.dataset.tab);
    });
    setEnfTab(S.enfTab || "wrongside");
  }
  const dwell = (s) => (Number.isFinite(num(s)) && num(s) > 0 ? Math.round(num(s)) + " s" : "not measured");

  async function renderParking() {
    const elScope = $("parking-scope");
    const elCases = $("parking-cases");
    if (!elCases) return;
    try {
      const data = await getJSON("/api/parking/cases");
      const cases = (Array.isArray(data) ? data : (data.cases || [])).slice().sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
      const open = cases.filter((c) => !["closed", "vehicle_moved", "towed"].includes(c.state));
      if (elScope) elScope.textContent = "· " + plural(cases.length, "case") + " · " + open.length + " open · " + cases.filter((c) => c.towing_authorized).length + " towing authorised";
      $("parking-count").textContent = open.length ? String(open.length) : "";
      const newBtn = el("button", { class: "btn", type: "button", text: "Open a parking case", onclick: () => newParkingForm() });
      if (!cases.length) {
        elCases.replaceChildren(el("div", { class: "empty" }, el("p", null, el("b", { text: "No parking cases." }),
          " Cases are opened by an officer from a vehicle in a stored analysis. Fixed cameras with configured zones can be scanned for stationary vehicles first."), newBtn));
        return;
      }
      elCases.replaceChildren(el("div", { class: "table-tools" }, newBtn), el("table", { class: "cases" },
        el("thead", null, el("tr", null, ...["Case", "Vehicle", "Zone / location", "Dwell", "Status", ""].map((h) => el("th", { text: h })))),
        el("tbody", null, ...cases.map((c) => {
          const tr = el("tr", { "data-href": "1", tabindex: "0" },
            el("td", { class: "clip", text: c.case_id }, el("small", { class: "sub", text: (c.clip_id || "") + (c.track_id != null ? " · T" + c.track_id : "") })),
            el("td", null, c.registration_number ? plateEl(c.registration_number) : el("span", { class: "muted", text: "No confident plate match" }),
              el("small", { class: "sub", text: [cap(c.colour), c.vehicle_type].filter((x) => x && x !== "Unknown" && x !== "unknown").join(" ") })),
            el("td", null, (c.zone_name || cap(c.violation_type)), el("small", { class: "sub", text: c.location || "" })),
            el("td", { class: "num", text: dwell(c.dwell_duration_s) }),
            el("td", null, el("span", { class: "tag " + PARK_TONE(c.state), text: PARK_LABEL[c.state] || cap(c.state) })),
            el("td", { class: "go", text: "→" }));
          tr.addEventListener("click", () => showParkingDetails(c));
          tr.addEventListener("keydown", (e) => { if (e.key === "Enter") showParkingDetails(c); });
          return tr;
        }))));
    } catch (e) {
      elCases.replaceChildren(pad("Couldn't load parking cases: " + e.message));
    }
  }

  async function newParkingForm() {
    setEnfTab("parking");
    const meta = await enfMeta();
    const clips = (S.overview && S.overview.clips) || [];
    const runSel = el("select", { class: "field", "aria-label": "Stored analysis" }, ...clips.map((c) => el("option", { value: "runs/" + c.clip_id, text: c.clip_id + " · " + cap(c.camera_type) })));
    const trackSel = el("select", { class: "field", "aria-label": "Vehicle" });
    const typeSel = el("select", { class: "field", "aria-label": "Violation type" },
      ...Object.entries((meta && meta.parking.violations) || {}).map(([k, v]) => el("option", { value: k, text: v.title + " · " + inr(v.fine_inr) })));
    const loc = el("input", { class: "field", placeholder: "Location (e.g. Sector 29 market, east kerb)", maxlength: 120, "aria-label": "Location" });
    const scan = el("div", { class: "scan", "aria-live": "polite" });
    const msg = el("p", { class: "ev-note", role: "status" });
    let scanned = null;
    const loadRun = async () => {
      trackSel.replaceChildren(el("option", { text: "Loading…" }));
      scan.replaceChildren(el("p", { class: "muted small", text: "Checking the camera's parking zones…" }));
      const [res, sc] = await Promise.all([getJSON("/data/" + runSel.value + "/result.json").catch(() => null), getJSON("/api/parking/scan/" + runSel.value).catch(() => null)]);
      scanned = sc;
      const vs = (res && res.vehicles) || [];
      trackSel.replaceChildren(...vs.map((v) => el("option", { value: v.track_id,
        text: "T" + v.track_id + " · " + [cap((v.colour || {}).label), (v.type || {}).label].filter(Boolean).join(" ") + " · " + ((v.plate || {}).fused || "plate not read") + (v.decision === "match" ? " · matched" : "") })));
      if (!sc) { scan.replaceChildren(el("p", { class: "muted small", text: "Zone check unavailable." })); return; }
      if (!sc.assessed) {
        scan.replaceChildren(el("p", { class: "flash", text: "Automatic dwell check not available for this clip: " + sc.not_assessed_reason + ". You can still open a case from your own observation; it starts at ‘Detected’ and must be verified." }));
        return;
      }
      scan.replaceChildren(el("p", { class: "muted small", text: "Zones: " + sc.zones.map((z) => z.name + " (" + cap(z.type) + ", limit " + z.dwell_limit_s + " s)").join(" · ") }),
        sc.findings.length ? el("ul", { class: "reasons" }, ...sc.findings.map((f) => el("li", null, "T" + f.track_id + ": " + cap(f.status) + (f.duration_s != null ? " · " + f.duration_s + " s" : "") + " · " + f.zone_name)))
          : el("p", { class: "muted small", text: "No tracked vehicle stayed inside a zone." }));
    };
    runSel.addEventListener("change", loadRun);
    const go = el("button", { class: "btn", type: "button", text: "Open case" , onclick: () => {
      const tid = Number(trackSel.value);
      const f = scanned && scanned.findings ? scanned.findings.find((x) => x.track_id === tid) : null;
      runAction(msg, () => post("/api/parking/cases", { run_id: runSel.value, track_id: tid, violation_type: typeSel.value, location: loc.value,
        analysis_result: f ? { violation_type: f.violation_type || typeSel.value, duration_s: f.duration_s, zone_name: f.zone_name } : undefined }), showParkingDetails);
    } });
    $("enf-evidence").replaceChildren(...evHead("Parking", "Open a parking case", "Pick the vehicle from a stored analysis. Its plate match, type and colour come from that analysis, never from this form."),
      el("div", { class: "lookup" }, el("label", { class: "fl" }, "Stored analysis", runSel), el("label", { class: "fl" }, "Vehicle", trackSel),
        el("label", { class: "fl" }, "Violation", typeSel), el("label", { class: "fl" }, "Location", loc), scan, go, msg));
    if (clips.length) loadRun(); else scan.replaceChildren(pad("No stored analyses."));
  }

  async function showParkingDetails(c) {
    const ev = $("enf-evidence");
    if (!ev) return;
    setEnfTab("parking");
    const meta = await enfMeta();
    const next = ((meta && meta.parking.transitions[c.state]) || []).slice().sort((a, b) => (a === "closed") - (b === "closed"));
    const needsReason = new Set((meta && meta.parking.needs_reason) || []);
    const warn = c.warning_notice || {};
    const note = el("input", { class: "field", placeholder: "Note / reason (required to authorise towing or record issuance)", maxlength: 300, "aria-label": "Note" });
    const msg = el("p", { class: "ev-note", role: "status" });
    const act = (st) => el("button", { class: "btn" + (st === "closed" || st === "disputed" ? " ghost" : "") + (st === "towing_authorised" ? " danger" : ""), type: "button",
      text: PARK_ACTION[st] || cap(st),
      onclick: () => {
        if (needsReason.has(st) && !note.value.trim()) { msg.textContent = "Write the reason for this decision in the note field first."; note.focus(); return; }
        runAction(msg, () => post("/api/parking/cases/" + c.case_id + "/transition", { new_state: st, officer: officerName(), note: note.value }), showParkingDetails);
      } });
    const draftBtn = c.state === "echallan_pending" ? el("button", { class: "btn ghost", type: "button", text: "Draft the e-challan", onclick: () => {
      if (!c.registration_number) { msg.textContent = "No confident registry match for this vehicle, so no e-challan can be drafted against a registration."; return; }
      runAction(msg, () => post("/api/echallans/cases", { registration_number: c.registration_number,
        violation_category: c.violation_type === "tow_away" ? "Tow-away obstruction" : c.violation_type === "emergency_access" ? "Emergency route obstruction" : "Illegal parking",
        location: c.location, evidence_run: c.run_id, track_id: c.track_id, officer_id: officerName(), notes: "From parking case " + c.case_id }),
      (d) => { setEnfTab("echallan"); showEChallanDetails(d); });
    } }) : null;
    ev.replaceChildren(...[
      flashNode(),
      ...evHead("Parking case", c.case_id, (c.violation_title || cap(c.violation_type)) + " · " + (c.legal_section || "")),
      el("ol", { class: "steps" }, ...["detected", "verified_violation", "warning_sent", "violation_unresolved", "towing_authorised"].map((s) => {
        const order = ["detected", "pending_verification", "verified_violation", "owner_notification_pending", "warning_sent", "violation_unresolved", "echallan_pending", "towing_authorised", "towed"];
        const done = order.indexOf(c.state) >= order.indexOf(s) || (c.audit_trail || []).some((a) => a.to_state === s);
        return el("li", { class: done ? "done" : null, "aria-current": c.state === s ? "step" : null, text: PARK_LABEL[s] });
      })),
      section("Vehicle and place", null, kv([
        ["Registration", c.registration_number ? plateEl(c.registration_number) : "No confident registry match"],
        ["Vehicle", [cap(c.colour), c.vehicle_type].filter((x) => x && !/^unknown$/i.test(x)).join(" ") || "—"],
        ["Evidence", c.run_id && c.run_id !== "runs/manual" ? el("a", { class: "more", href: "#case/" + c.run_id, text: (c.clip_id || c.run_id) + " · vehicle T" + c.track_id }) : "—"],
        ["Zone", c.zone_name || "—"], ["Location", c.location || "—"], ["Dwell measured", dwell(c.dwell_duration_s)],
        ["Fine (if issued)", c.fine_inr ? inr(c.fine_inr) : "—"], ["Status", el("span", { class: "tag " + PARK_TONE(c.state), text: PARK_LABEL[c.state] || cap(c.state) })],
        ["Towing authorised", c.towing_authorized ? "Yes, by an officer" : "No"],
        c.recheck ? ["Recheck", c.recheck.seconds_after_warning + " s after the warning · grace period " + (c.recheck.grace_period_elapsed ? "had run out" : "had NOT run out")] : null,
      ])),
      warn.warning_message ? section("Owner warning", "simulated · not sent anywhere", el("div", { class: "flash" },
        el("p", { style: "margin:0 0 6px", text: warn.warning_message }),
        el("small", { class: "muted", text: "Response period: " + (warn.response_period_minutes ?? "—") + " min · " + (warn.disclaimer || "") }))) : null,
      next.length ? section("Next step", "the server only allows these moves", el("div", { class: "lookup" }, note, el("div", { class: "btn-row" }, ...next.map(act), draftBtn), msg))
        : section("Next step", null, el("p", { class: "ev-note", text: "This case is final." })),
      section("Audit trail", null, el("ul", { class: "reasons" }, ...(c.audit_trail || []).map((a) => el("li", null, (a.timestamp || "").replace("T", " ") + " · " + a.officer + " · " + (PARK_LABEL[a.to_state] || a.to_state) + (a.action && !/^Status changed/.test(a.action) ? ": " + a.action : ""))))),
    ].filter(Boolean));
  }

  async function renderEChallans() {
    const elScope = $("echallan-scope");
    const elCases = $("echallan-cases");
    if (!elCases) return;
    try {
      const data = await getJSON("/api/echallans/cases");
      const cases = (Array.isArray(data) ? data : (data.cases || [])).slice().sort((a, b) => (b.timestamp || "").localeCompare(a.timestamp || ""));
      const waiting = cases.filter((c) => ["draft", "pending_review", "disputed"].includes(c.status)).length;
      if (elScope) elScope.textContent = "· " + plural(cases.length, "case") + " · " + waiting + " need an officer";
      $("echallan-count").textContent = waiting ? String(waiting) : "";
      const filter = el("select", { class: "field compact", "aria-label": "Filter by status" }, el("option", { value: "", text: "All statuses" }),
        ...Object.entries(ECH_LABEL).map(([k, v]) => el("option", { value: k, text: v, selected: S.echFilter === k ? true : null })));
      filter.addEventListener("change", () => { S.echFilter = filter.value; renderEChallans(); });
      const shown = S.echFilter ? cases.filter((c) => c.status === S.echFilter) : cases;
      const tools = el("div", { class: "table-tools" }, el("button", { class: "btn", type: "button", text: "Draft an e-challan", onclick: () => newEChallanForm() }), filter);
      if (!shown.length) {
        elCases.replaceChildren(tools, el("div", { class: "empty" }, el("p", null, el("b", { text: cases.length ? "No cases with this status." : "No e-challan cases." }),
          cases.length ? "" : " Drafts come from a parking case, or are written by an officer against a vehicle in a stored analysis. Each one needs evidence verification and a named approving officer.")));
        return;
      }
      elCases.replaceChildren(tools, el("table", { class: "cases" },
        el("thead", null, el("tr", null, ...["Case", "Registration", "Violation", "Fine", "Status", ""].map((h) => el("th", { text: h })))),
        el("tbody", null, ...shown.map((c) => {
          const tr = el("tr", { "data-href": "1", tabindex: "0" },
            el("td", { class: "clip", text: c.case_id }, el("small", { class: "sub", text: (c.timestamp || "").replace("T", " ") })),
            el("td", null, plateEl(c.registration_number || "?")),
            el("td", null, c.violation_category, el("small", { class: "sub", text: c.legal_provision })),
            el("td", { class: "num", text: inr(c.fine_inr) }),
            el("td", null, el("span", { class: "tag " + ECH_TONE(c.status), text: ECH_LABEL[c.status] || cap(c.status) })),
            el("td", { class: "go", text: "→" }));
          tr.addEventListener("click", () => showEChallanDetails(c));
          tr.addEventListener("keydown", (e) => { if (e.key === "Enter") showEChallanDetails(c); });
          return tr;
        }))));
    } catch (e) {
      elCases.replaceChildren(pad("Couldn't load e-challan cases: " + e.message));
    }
  }

  async function newEChallanForm() {
    setEnfTab("echallan");
    const meta = await enfMeta();
    const clips = (S.overview && S.overview.clips) || [];
    const runSel = el("select", { class: "field", "aria-label": "Stored analysis" }, ...clips.map((c) => el("option", { value: "runs/" + c.clip_id, text: c.clip_id })));
    const trackSel = el("select", { class: "field", "aria-label": "Vehicle" });
    const cat = el("select", { class: "field", "aria-label": "Violation" }, ...Object.entries((meta && meta.echallan.categories) || {}).map(([k, v]) => el("option", { value: k, text: k + " · " + inr(v.fine_inr) })));
    const loc = el("input", { class: "field", placeholder: "Location", maxlength: 120, "aria-label": "Location" });
    const msg = el("p", { class: "ev-note", role: "status" });
    let vehicles = [];
    const loadRun = async () => {
      const res = await getJSON("/data/" + runSel.value + "/result.json").catch(() => null);
      vehicles = ((res && res.vehicles) || []).filter((v) => v.decision === "match" && (v.candidates || []).length);
      trackSel.replaceChildren(...(vehicles.length ? vehicles.map((v) => el("option", { value: v.track_id, text: "T" + v.track_id + " · " + v.candidates[0].registration_number + " · " + [cap((v.colour || {}).label), (v.type || {}).label].filter(Boolean).join(" ") }))
        : [el("option", { value: "", text: "No vehicle with a confident registry match in this clip" })]));
    };
    runSel.addEventListener("change", loadRun);
    const go = el("button", { class: "btn", type: "button", text: "Create draft", onclick: () => {
      const v = vehicles.find((x) => String(x.track_id) === trackSel.value);
      if (!v) { msg.textContent = "Choose a vehicle with a confident registry match. A challan is never drafted against an uncertain plate."; return; }
      runAction(msg, () => post("/api/echallans/cases", { registration_number: v.candidates[0].registration_number, violation_category: cat.value,
        location: loc.value, evidence_run: runSel.value, track_id: v.track_id, officer_id: officerName() }), showEChallanDetails);
    } });
    $("enf-evidence").replaceChildren(...evHead("E-challan", "Draft an e-challan", "Only vehicles with a confident registry match are offered. The plate, OCR confidence, type and colour are copied from the stored analysis."),
      el("div", { class: "lookup" }, el("label", { class: "fl" }, "Stored analysis", runSel), el("label", { class: "fl" }, "Vehicle", trackSel),
        el("label", { class: "fl" }, "Violation", cat), el("label", { class: "fl" }, "Location", loc), go, msg));
    if (clips.length) loadRun();
  }

  function showEChallanDetails(c) {
    const ev = $("enf-evidence");
    if (!ev) return;
    setEnfTab("echallan");
    const dsp = c.dispute_record;
    const va = c.vehicle_attributes || {};
    const er = c.evidence_reference || {};
    const text = el("input", { class: "field", placeholder: "Reason / findings / note", maxlength: 300, "aria-label": "Reason or findings" });
    const msg = el("p", { class: "ev-note", role: "status" });
    const base = "/api/echallans/cases/" + c.case_id;
    const need = (what) => { if (!text.value.trim()) { msg.textContent = "Write the " + what + " first."; text.focus(); return false; } return true; };
    const B = (label, cls, fn) => el("button", { class: "btn" + (cls ? " " + cls : ""), type: "button", text: label, onclick: fn });
    const acts = [];
    if (c.status === "draft") acts.push(B("Verify evidence", "", () => runAction(msg, () => post(base + "/verify", { officer: officerName(), notes: text.value }), showEChallanDetails)));
    if (["draft", "pending_review", "approved"].includes(c.status)) acts.push(B("Approve and issue (simulated)", c.status === "draft" ? "ghost" : "", () => runAction(msg, () => post(base + "/approve", { officer: officerName(), notes: text.value }), showEChallanDetails)));
    if (c.status === "issued") {
      acts.push(B("Record payment (simulated)", "", () => runAction(msg, () => post(base + "/pay", {}), showEChallanDetails)));
      acts.push(B("Record citizen dispute", "ghost", () => need("dispute reason") && runAction(msg, () => post(base + "/dispute", { reason: text.value }), showEChallanDetails)));
    }
    if (c.status === "disputed") {
      acts.push(B("Uphold dispute (cancel challan)", "", () => need("findings") && runAction(msg, () => post(base + "/resolve_dispute", { resolution: "upheld", officer: officerName(), findings: text.value }), showEChallanDetails)));
      acts.push(B("Dismiss dispute (challan stands)", "ghost", () => need("findings") && runAction(msg, () => post(base + "/resolve_dispute", { resolution: "dismissed", officer: officerName(), findings: text.value }), showEChallanDetails)));
    }
    if (["draft", "pending_review", "approved", "issued"].includes(c.status)) acts.push(B("Cancel", "ghost", () => need("cancellation reason") && runAction(msg, () => post(base + "/cancel", { officer: officerName(), reason: text.value }), showEChallanDetails)));
    const steps = ["draft", "pending_review", "issued", "paid"];
    ev.replaceChildren(...[
      flashNode(),
      ...evHead("E-challan", c.case_id, (c.violation_category || "Violation") + " · " + (c.legal_provision || "")),
      el("ol", { class: "steps" }, ...steps.map((s) => el("li", { class: steps.indexOf(c.status) >= steps.indexOf(s) || (s === "issued" && c.issued_at) ? "done" : null,
        "aria-current": c.status === s ? "step" : null, text: { draft: "Draft", pending_review: "Verified", issued: "Approved & issued", paid: "Paid" }[s] }))),
      c.status === "cancelled" || c.status === "disputed" ? el("p", { class: "flash", text: c.status === "cancelled" ? "Cancelled: " + (c.cancellation_reason || "") : "Disputed: waiting for an adjudicating officer." }) : null,
      section("Case", null, kv([
        ["Registration", plateEl(c.registration_number || "?")], ["Fine", inr(c.fine_inr)],
        ["Status", el("span", { class: "tag " + ECH_TONE(c.status), text: ECH_LABEL[c.status] || cap(c.status) })],
        ["Payment", c.payment_status === "paid_simulated" ? "Paid (simulated) · " + (c.payment_reference || "") : cap(c.payment_status || "unpaid")],
        ["Evidence verified by", c.verified_by || "Not yet"], ["Approved by", c.approved_by || "Not yet"],
        ["Location", c.location || "—"], ["Created", (c.timestamp || "").replace("T", " ")],
      ])),
      section("Evidence", "copied from the stored analysis", kv([
        ["Plate read", va.ocr_plate ? plateEl(va.ocr_plate) : "—"],
        ["OCR confidence", va.ocr_confidence != null ? pct(va.ocr_confidence, 1) + " (mean fused per-character)" : "not recorded"],
        ["Vehicle", [cap(va.colour), va.type].filter(Boolean).join(" ") || "—"],
        ["Clip", er.run_id ? el("a", { class: "more", href: "#case/" + er.run_id, text: er.run_id.replace("runs/", "") + (er.track_id != null ? " · vehicle T" + er.track_id : "") }) : "No stored evidence linked"],
        ["Frames", er.frames ? er.frames.join("–") : "—"],
      ])),
      dsp ? section("Citizen dispute", dsp.dispute_id, kv([["Claim", dsp.reason], ["Filed", (dsp.filed_at || "").replace("T", " ")],
        ["Outcome", dsp.resolution ? cap(dsp.resolution) + " by " + dsp.adjudicated_by + (dsp.findings ? ": " + dsp.findings : "") : "Under review"]])) : null,
      acts.length ? section("Officer action", null, el("div", { class: "lookup" }, text, el("div", { class: "btn-row" }, ...acts), msg))
        : section("Officer action", null, el("p", { class: "ev-note", text: "This case is final." })),
      section("Audit history", null, el("ul", { class: "reasons" }, ...(c.audit_history || []).map((a) => el("li", null, (a.timestamp || "").replace("T", " ") + " · " + a.officer + " · " + cap(a.action.toLowerCase()) + (a.details ? ": " + a.details : ""))))),
      el("p", { class: "demo-banner small", text: (c.legal_notice || "Simulated e-challan.") + " No payment gateway or government system is connected." }),
    ].filter(Boolean));
  }
  async function renderAudit() {
    const r = await apiCall("/api/audit");
    if (!r.ok) { $("audit").replaceChildren(pad(r.error)); return; }
    const rows = r.data.slice(0, 40);
    $("audit").replaceChildren(rows.length ? el("table", { class: "cases" },
      el("thead", null, el("tr", null, ...["When", "Action", "Registration / item", "Reason / note", "Context", "Outcome"].map((h) => el("th", { text: h })))),
      el("tbody", null, ...rows.map((e) => el("tr", null, el("td", { class: "muted", text: (e.at || "").replace("T", " ") }),
        el("td", { text: e.action + (e.violation ? ": " + e.violation : "") }), el("td", { class: "clip", text: e.registration || e.violation_id || "" }),
        el("td", { class: "muted", text: e.reason || e.note || "" }), el("td", { class: "muted", text: e.context || "" }), el("td", { text: e.outcome }))))) : pad("No activity yet."));
  }
  function manualLookup() {
    S.enfSel = null;
    S.enfManual = true;
    document.querySelectorAll("#ws-list .metric").forEach((b) => b.removeAttribute("aria-current"));
    const input = el("input", { class: "field mono", placeholder: "e.g. DL3CCY1025", "aria-label": "Registration number", maxlength: 12, autocomplete: "off", spellcheck: "false" });
    const holder = el("div");
    const form = lookupForm(async (reason, msg) => {
      const reg = input.value.toUpperCase().replace(/[^A-Z0-9]/g, "");
      if (!reg) { msg.textContent = "Type a registration number."; input.focus(); return; }
      msg.textContent = "Looking up…";
      const r = await apiCall("/api/intel/" + encodeURIComponent(reg) + "?" + new URLSearchParams({ reason }));
      msg.textContent = r.ok ? "" : r.error;
      const after = async () => {
        const again = await apiCall("/api/intel/" + encodeURIComponent(reg) + "?" + new URLSearchParams({ reason: "Refresh after change" }));
        if (again.ok) holder.replaceChildren(...recordNodes(again.data, "", after));
        await openEnforcement();
      };
      holder.replaceChildren(...(r.ok ? recordNodes(r.data, "", after) : []));
      renderAudit();
    }, "Look up");
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") form.querySelector(".btn").click(); });
    form.prepend(input);
    $("enf-evidence").replaceChildren(...[flashNode(), ...evHead("Look up a vehicle", "Registration lookup", "Shows everything on record for a registration, and lets you issue a simulated challan for it."), form, holder].filter(Boolean));
  }
  function selectViolation(x) {
    S.enfSel = x.violation_id;
    S.enfManual = false;
    document.querySelectorAll("#ws-list .metric").forEach((b) => b.setAttribute("aria-current", String(b.dataset.k === x.violation_id)));
    const m = x.measurement;
    const crops = (S.enfFiles[x.run] || []).filter((f) => f.startsWith("t" + x.track_id + "_vehicle_"));
    const msg = el("p", { class: "ev-note", role: "status" });
    const note = el("input", { class: "field", placeholder: "Note (optional)", maxlength: 300, "aria-label": "Review note" });
    const act = (decision) => async () => {
      const r = await apiCall("/api/violations/review", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ violation_id: x.violation_id, decision, note: note.value }) });
      if (!r.ok) { msg.textContent = r.error; return; }
      S.rec.clear();
      const who = x.clip_id + " T" + x.track_id;
      S.enfFlash = decision === "pending" ? who + " is back in the queue."
        : (decision === "confirmed" ? "Confirmed " : "Rejected ") + who + ". " +
          (r.data.challan ? "Simulated challan " + r.data.challan.challan_id + " raised." : (r.data.message || "").replace(/^(confirmed|rejected)\.\s*/i, ""));
      if (decision !== "pending") {
        // Move on to the next item still waiting for review (or the lookup when none are left).
        const ids = S.enfPending || [];
        const i = ids.indexOf(x.violation_id);
        const next = ids.slice(i + 1).concat(ids.slice(0, Math.max(i, 0))).find((id) => id !== x.violation_id);
        S.enfSel = next || null;
        S.enfManual = false;
      }
      await openEnforcement();
    };
    const isPending = x.review.status === "pending";
    $("enf-evidence").replaceChildren(...[
      flashNode(),
      evHead("Suspected violation", x.label, x.clip_id + " · vehicle T" + x.track_id + " · " + clock(x.time_s[0]) + "–" + clock(x.time_s[1])),
      crops.length ? el("div", { class: "crops" }, ...crops.slice(0, 3).map((f) => el("img", { src: "/data/" + x.run + "/vehicles/" + f, alt: "Vehicle crop", style: "height:64px" }))) : null,
      section("Vehicle", null, kv([["Plate read", x.plate ? plateEl(x.plate) : "not read"], ["Registry", x.registration_number ? plateEl(x.registration_number) : "no confident match"],
        ["Type / colour", [x.vehicle_type, x.colour].filter(Boolean).join(" · ")]])),
      m.method === "head_on_pass" ? section("Measured", "moving camera · head-on pass", ...headOnNodes(m, (x.time_s[1] && x.evidence_frames[2] / x.time_s[1]) || 30), el("p", { class: "ev-note", text: "Road layout: " + cap(m.layout) }))
        : section("Measured", null, dirs(m, true), kv([["Angle off permitted", deg(m.cos_to_allowed) + "°"], ["Steps against the flow", pct(m.against_flow_share)], ["Zone", m.zone]])),
      section("Review", null, kv([["Status", reviewTag(x.review.status)], ["Note", x.review.note]]),
        isPending
          ? el("div", { class: "lookup" }, note, el("div", { class: "btn-row" },
            el("button", { class: "btn", type: "button", text: "Confirm", onclick: act("confirmed") }),
            el("button", { class: "btn ghost", type: "button", text: "Reject", onclick: act("rejected") })), msg)
          : el("div", { class: "lookup" }, el("p", { class: "ev-note", text: "Reviewed. It has left the queue." }),
            el("button", { class: "btn ghost", type: "button", text: "Reset to pending", onclick: act("pending") }), msg)),
      el("div", { class: "link-row-plain" },
        el("a", { class: "more", href: "#case/" + x.run, text: "Open the case and play the clip" }),
        el("button", { class: "more", type: "button", text: "Registration lookup", onclick: manualLookup })),
    ].flat().filter(Boolean));
  }

  async function initMeta() {
    try { S.meta = await getJSON("/api/intel/meta"); } catch (_) { S.meta = null; }
  }

  /* ---------------------------------------------------------------- video + overlay */
  function setupVideo() {
    const video = $("video");
    video.pause();
    video.src = S.route.base + "/video";
    $("no-video").hidden = true;
    $("overlay").hidden = false;
    $("play").disabled = false;
    video.onerror = () => { $("no-video").hidden = false; $("overlay").hidden = true; $("play").disabled = true; };
    video.onloadedmetadata = () => { fit(video, $("overlay")); draw(); tick(); };
    video.load();
  }
  function fit(video, canvas) {
    canvas.style.left = video.offsetLeft + "px";
    canvas.style.top = video.offsetTop + "px";
    canvas.style.width = video.clientWidth + "px";
    canvas.style.height = video.clientHeight + "px";
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(video.clientWidth * dpr);
    canvas.height = Math.round(video.clientHeight * dpr);
  }
  /* Box for a track at a frame: last recorded entry at or before it, if recent enough. Entries are [frame, x1, y1, x2, y2]. */
  function boxAt(track, frame) {
    let lo = 0, hi = track.length - 1, hit = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (track[m][0] <= frame) { hit = m; lo = m + 1; } else hi = m - 1; }
    return hit >= 0 && frame - track[hit][0] <= 6 ? track[hit] : null;
  }
  function paint(canvas, video, srcW, boxes) {
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const k = video.clientWidth / (srcW || video.videoWidth || 1);
    const css = getComputedStyle(document.documentElement);
    const mark = css.getPropertyValue("--mark").trim() || "#f2c230";
    boxes.forEach(({ b, label, on }) => {
      const [x, y, w, h] = [b[1] * k, b[2] * k, (b[3] - b[1]) * k, (b[4] - b[2]) * k];
      ctx.lineWidth = on ? 3 : 1.25;
      ctx.strokeStyle = on ? mark : "rgba(255,255,255,.75)";
      ctx.strokeRect(x, y, w, h);
      if (!label) return;
      ctx.font = (on ? "600 " : "500 ") + "12px " + css.getPropertyValue("--mono");
      const tw = ctx.measureText(label).width + 10;
      const ly = y > 20 ? y - 20 : y;
      ctx.fillStyle = on ? mark : "rgba(20,22,26,.72)";
      ctx.fillRect(x - (on ? 1.5 : .6), ly, tw, 19);
      ctx.fillStyle = on ? "#14161a" : "#fff";
      ctx.fillText(label, x + 5 - (on ? 1.5 : .6), ly + 14);
    });
  }
  function currentFrame(video, result) {
    const fps = num(result && result.video && result.video.fps) || 30;
    return Math.round(video.currentTime * fps);
  }
  function draw() {
    const video = $("video");
    if (!S.result || !video.videoWidth) return;
    const frame = currentFrame(video, S.result);
    const boxes = [];
    (S.result.vehicles || []).forEach((v) => {
      const b = boxAt(S.boxes.get(v.track_id) || [], frame);
      if (b) boxes.push({ b, on: v.track_id === S.vid, label: v.track_id === S.vid ? (v.plate && v.plate.fused) || "T" + v.track_id : "T" + v.track_id });
    });
    boxes.sort((a, b) => a.on - b.on);
    paint($("overlay"), video, S.result.video && S.result.video.width, boxes);
  }
  function tick() {
    const video = $("video");
    const d = video.duration;
    const t = video.currentTime;
    $("progress").style.width = (d ? (t / d) * 100 : 0) + "%";
    $("seek").value = d ? Math.round((t / d) * 1000) : 0;
    $("time").textContent = clock(t) + " / " + clock(d);
    $("play").textContent = video.paused ? "▶" : "❚❚";
    $("play").setAttribute("aria-label", video.paused ? "Play" : "Pause");
    draw();
  }
  function loop() { tick(); if (!$("video").paused) requestAnimationFrame(loop); }
  function seekFrame(frame) {
    const video = $("video");
    const fps = num(S.result.video && S.result.video.fps) || 30;
    if (!video.readyState) return;
    video.pause();
    video.currentTime = frame / fps + 0.001;
    $("player").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  function renderTicks(v) {
    const frames = num(S.result.video && S.result.video.frames);
    const reads = (v.plate && v.plate.per_frame_reads) || [];
    $("ticks").replaceChildren(...(frames ? reads.map((r) => el("i", { style: "left:" + (r.frame / frames) * 100 + "%" })) : []));
  }
  function initPlayer() {
    const video = $("video");
    const toggle = () => { if (video.readyState) (video.paused ? video.play() : video.pause()); };
    $("play").addEventListener("click", toggle);
    video.addEventListener("play", loop);
    ["pause", "seeked", "timeupdate"].forEach((e) => video.addEventListener(e, tick));
    $("seek").addEventListener("input", () => { if (video.duration) video.currentTime = ($("seek").value / 1000) * video.duration; });
    $("overlay").addEventListener("click", (e) => {
      if (!S.result) return;
      const rect = $("overlay").getBoundingClientRect();
      const k = video.clientWidth / ((S.result.video && S.result.video.width) || video.videoWidth);
      const x = (e.clientX - rect.left) / k, y = (e.clientY - rect.top) / k;
      const frame = currentFrame(video, S.result);
      let best = null, area = Infinity;
      (S.result.vehicles || []).forEach((v) => {
        const b = boxAt(S.boxes.get(v.track_id) || [], frame);
        if (b && x >= b[1] && x <= b[3] && y >= b[2] && y <= b[4] && (b[3] - b[1]) * (b[4] - b[2]) < area) { best = v; area = (b[3] - b[1]) * (b[4] - b[2]); }
      });
      if (best) selectVehicle(best.track_id, false); else toggle();
    });
    document.addEventListener("keydown", (e) => {
      if ($("view-case").hidden || /INPUT|SELECT|TEXTAREA|BUTTON/.test(document.activeElement.tagName)) return;
      if (e.key === " ") { e.preventDefault(); toggle(); }
    });
    window.addEventListener("resize", () => {
      if (!$("view-case").hidden && video.videoWidth) { fit(video, $("overlay")); draw(); }
      if (!$("view-crosscam").hidden) ccFitAll();
    });
  }

  /* ---------------------------------------------------------------- cross-camera */
  async function loadReview() {
    if (!S.review) S.review = await getJSON("/api/review");
    return S.review;
  }
  function pairLinks(pair) {
    if (pair.same_scene && Array.isArray(pair.same_scene.links)) {
      return pair.same_scene.links.map((l) => ({ a: l.a, b: l.b, status: l.link, score: l.link_score, reasons: l.evidence || [], final: l.final }));
    }
    const seen = new Set(), out = [];
    (pair.directions || []).forEach((d) => (d.links || []).forEach((l) => {
      if (!l.linked_to) return;
      const a = { clip_id: l.clip_id, track_id: l.track_id, plate: l.plate }, b = { clip_id: l.linked_to.clip_id, track_id: l.linked_to.track_id, plate: null };
      const key = [a.clip_id + a.track_id, b.clip_id + b.track_id].sort().join("|");
      if (seen.has(key)) return;
      seen.add(key);
      out.push({ a, b, status: (l.linked_to.evidence || "link"), score: l.linked_to.link_score, reasons: l.linked_to.reasons || [], parts: l.linked_to.parts, reason: l.decision_reason });
    }));
    return out;
  }
  async function openCrosscam() {
    try {
      const review = await loadReview();
      const pairs = review.crosscam_pairs || [];
      if (!pairs.length) { $("cc-state").textContent = "No cross-camera pairs have been analysed yet."; return; }
      const sel = $("pair");
      if (!sel.options.length) {
        pairs.forEach((p, i) => sel.append(el("option", { value: i, text: p.clip_a + " ↔ " + p.clip_b + (p.same_scene ? " · same scene" : "") })));
        sel.addEventListener("change", () => showPair(Number(sel.value)));
      }
      $("cc-state").hidden = true;
      $("cc").hidden = false;
      showPair(S.cc.pair ?? 0);
    } catch (e) {
      $("cc-state").className = "state-msg is-error";
      $("cc-state").textContent = "Cross-camera data couldn't be loaded. " + e.message;
    }
  }
  async function ccResult(clip) {
    if (!S.cc.results[clip]) S.cc.results[clip] = getJSON("/data/runs/" + clip + "/result.json").catch(() => null);
    return S.cc.results[clip];
  }
  async function showPair(i) {
    const pair = S.review.crosscam_pairs[i];
    S.cc.pair = i;
    $("pair").value = i;
    const links = pairLinks(pair);
    S.cc.links = links;
    $("cam-a").textContent = pair.clip_a;
    $("cam-b").textContent = pair.clip_b;
    [["va", pair.clip_a], ["vb", pair.clip_b]].forEach(([id, clip]) => {
      const v = $(id);
      v.pause();
      v.src = "/data/runs/" + clip + "/video";
      v.onloadedmetadata = () => { ccFitAll(); ccSeek(); };
      v.ontimeupdate = v.onseeked = ccDraw;
      v.load();
    });
    const [ra, rb] = await Promise.all([ccResult(pair.clip_a), ccResult(pair.clip_b)]);
    if (S.cc.pair !== i) return;
    S.cc.ra = ra; S.cc.rb = rb;
    $("link-list").replaceChildren(...links.map((l, n) => {
      const side = (s) => el("span", { class: "side" }, s.plate ? plateEl(s.plate) : el("span", { class: "muted", text: "plate not read" }), el("small", { text: s.clip_id + " · T" + s.track_id }));
      const strong = /^confirmed/i.test(String(l.status));
      return el("li", null, el("button", { class: "link-row", type: "button", "data-n": n, onclick: () => selectLink(n) },
        side(l.a), el("span", { class: "arrow", text: "↔" }), side(l.b),
        el("span", { class: "tag " + (strong ? "match" : "unsure"), text: strong ? "Confirmed" : "Probable" }), el("span", { class: "score", text: num(l.score).toFixed(1) })));
    }));
    if (!links.length) $("link-list").replaceChildren(el("li", { class: "muted", style: "padding:12px", text: "No links were made for this pair." }));
    const ss = pair.same_scene;
    $("cc-unlinked").textContent = ss ? "Not linked: " + plural((ss.unlinked_a || []).length, "track") + " in " + pair.clip_a + ", " + plural((ss.unlinked_b || []).length, "track") + " in " + pair.clip_b + ". " + (ss.note || "") : "";
    if (links.length) selectLink(0);
    else ["cc-evidence", "detail-a", "detail-b"].forEach((id) => $(id).replaceChildren());
  }
  const ccVehicle = (r, tid) => (r && (r.vehicles || []).find((x) => x.track_id === tid)) || null;
  /* What one camera saw on its own: its own track, plate reads, attributes and its own registry decision. */
  function clipDetail(v, r, side) {
    if (!v) return [el("p", { class: "muted small", text: side.clip_id + " T" + side.track_id + ": track details aren't available." })];
    const fps = num(r.video && r.video.fps) || 30;
    const p = v.plate || {};
    const reads = (p.per_frame_reads || []).length;
    const top = (v.candidates || []).slice().sort((a, b) => a.rank - b.rank)[0];
    const seek = (frame) => { const vid = side === S.cc.links[S.cc.link].a ? $("va") : $("vb"); if (vid.readyState) { vid.pause(); vid.currentTime = frame / fps + 0.001; } };
    return [
      el("div", { class: "cd-head" }, el("span", { class: "label", text: "This camera only" }), tag(v.decision)),
      el("div", { class: "cd-plate" }, p.fused ? plateEl(p.fused, true) : el("span", { class: "muted", text: "Plate not read" }),
        p.fused ? el("small", { class: "muted", text: X.knownCharacters(p.fused) + " of " + p.fused.length + " characters · " + plural(reads, "frame read") }) : null),
      kv([["Type", (v.type && v.type.label) ? v.type.label + (v.type.vote_share !== undefined ? " · " + pct(v.type.vote_share) + " of votes" : "") : "—"],
        ["Colour", cap(v.colour && v.colour.label) || "—"],
        ["Seen", clock(v.first_frame / fps) + " – " + clock(v.last_frame / fps) + " · " + plural(v.n_detections || 0, "detection")],
        ["Own top record", top ? el("span", null, plateEl(top.registration_number), " ", num(top.match_score).toFixed(1)) : "none"]]),
      v.decision_reason ? el("p", { class: "ev-note", text: cap(v.decision_reason) + "." }) : null,
      reads ? el("button", { class: "more", type: "button", text: "Jump to its best plate frame", onclick: () => seek(p.per_frame_reads[0].frame) }) : null,
    ];
  }
  /* Side by side: what each camera concluded alone, and the combined result from pooling both. */
  function compareTable(va, vb, l, f) {
    const cell = (x) => (x === null || x === undefined || x === "" ? el("span", { class: "muted", text: "—" }) : x);
    const plate = (v) => (v && v.plate && v.plate.fused ? plateEl(v.plate.fused) : null);
    const top = (v) => { const c = v && (v.candidates || []).slice().sort((a, b) => a.rank - b.rank)[0]; return c ? num(c.match_score).toFixed(1) : null; };
    const rows = [
      ["Plate", plate(va), plate(vb), f && f.plate ? plateEl(f.plate) : null],
      ["Type", va && va.type && va.type.label, vb && vb.type && vb.type.label, f && f.type],
      ["Colour", va && cap(va.colour && va.colour.label), vb && cap(vb.colour && vb.colour.label), f && cap(f.colour)],
      ["Plate reads", va && (va.plate && va.plate.per_frame_reads || []).length, vb && (vb.plate && vb.plate.per_frame_reads || []).length, f && f.reads_pooled],
      ["Best score", top(va), top(vb), f && f.match_score],
      ["Decision", va && tag(va.decision), vb && tag(vb.decision), f && f.decision ? tag(f.decision) : null],
    ];
    return el("table", { class: "compare" },
      el("thead", null, el("tr", null, el("th"), el("th", { text: l.a.clip_id }), el("th", { text: l.b.clip_id }), el("th", { class: "comb", text: "Combined" }))),
      el("tbody", null, ...rows.map(([k, a, b, c]) => el("tr", null, el("th", { text: k }), el("td", null, cell(a)), el("td", null, cell(b)), el("td", { class: "comb" }, cell(c))))));
  }
  function selectLink(n) {
    S.cc.link = n;
    document.querySelectorAll(".link-row").forEach((b) => b.setAttribute("aria-current", String(Number(b.dataset.n) === n)));
    const l = S.cc.links[n];
    const f = l.final;
    const va = ccVehicle(S.cc.ra, l.a.track_id), vb = ccVehicle(S.cc.rb, l.b.track_id);
    $("detail-a").replaceChildren(...clipDetail(va, S.cc.ra, l.a));
    $("detail-b").replaceChildren(...clipDetail(vb, S.cc.rb, l.b));
    $("cc-evidence").replaceChildren(...[
      evHead("Combined · both cameras", el("span", null, l.a.clip_id + " T" + l.a.track_id + "  ↔  " + l.b.clip_id + " T" + l.b.track_id), cap(l.reason || l.status) + ". Link score " + num(l.score).toFixed(1) + "."),
      section("Each camera, and combined", null, compareTable(va, vb, l, f)),
      l.parts ? section("Agreement", null, ...Object.entries(l.parts).map(([k, v]) => barRow(cap(k), v))) : null,
      section("Why they're linked", null, el("ul", { class: "reasons" }, ...l.reasons.map((r) => el("li", { class: X.classifyReason(r), text: r })))),
      f ? section("Combined registry result", "both cameras' reads pooled", kv([["Decision", f.decision ? tag(f.decision) : null],
        ["Top record", f.registry_top1 ? plateEl(f.registry_top1) : null], ["Match score", f.match_score]])) : null,
      f && f.reason ? el("p", { class: "ev-note", text: cap(f.reason) + "." }) : null,
      el("p", { class: "ev-note", text: "Link scores rank candidates; they are not probabilities. Only plate-confirmed links give an identity." }),
      ccRecord(l),
    ].flat().filter(Boolean));
    ccSeek();
  }
  function ccSeek() {
    const l = S.cc.links && S.cc.links[S.cc.link];
    if (!l) return;
    [["va", S.cc.ra, l.a.track_id], ["vb", S.cc.rb, l.b.track_id]].forEach(([id, r, tid]) => {
      const v = $(id);
      const veh = r && (r.vehicles || []).find((x) => x.track_id === tid);
      if (!veh || !v.readyState) return;
      const fps = num(r.video && r.video.fps) || 30;
      const best = veh.plate && veh.plate.per_frame_reads && veh.plate.per_frame_reads[0];
      v.pause();
      v.currentTime = (best ? best.frame : veh.first_frame) / fps + 0.001;
    });
  }
  function ccFitAll() { [["va", "ca"], ["vb", "cb"]].forEach(([v, c]) => { if ($(v).videoWidth) fit($(v), $(c)); }); ccDraw(); }
  function ccDraw() {
    const l = S.cc.links && S.cc.links[S.cc.link];
    [["va", "ca", S.cc.ra, "a"], ["vb", "cb", S.cc.rb, "b"]].forEach(([vid, cid, r, side]) => {
      const v = $(vid);
      if (!r || !v.videoWidth) return;
      const frame = currentFrame(v, r);
      const linked = new Map((S.cc.links || []).map((x, n) => [x[side].track_id, n]));
      const boxes = [];
      (r.vehicles || []).forEach((veh) => {
        if (!linked.has(veh.track_id)) return;
        const b = boxAt(veh.track || [], frame);
        const on = l && l[side].track_id === veh.track_id;
        if (b) boxes.push({ b, on, label: on ? (veh.plate && veh.plate.fused) || "T" + veh.track_id : null });
      });
      boxes.sort((a, b) => a.on - b.on);
      paint($(cid), v, r.video && r.video.width, boxes);
    });
  }
  function initCrosscam() {
    ["va", "vb"].forEach((id) => {
      const v = $(id);
      v.parentElement.addEventListener("click", () => { if (v.readyState) (v.paused ? v.play() : v.pause()); });
      v.addEventListener("play", function frame() { ccDraw(); if (!v.paused) requestAnimationFrame(frame); });
    });
  }

  /* ---------------------------------------------------------------- performance */
  const METRIC_INFO = {
    registered_matches: ["Registered vehicles matched", "Vehicles whose plate is in the registry and that the system matched to the right record."],
    false_confident_matches: ["False confident matches", "Vehicles not in the registry that still got a confident match. Zero means no identity was invented."],
    wrong_plate_characters: ["Wrong plate characters", "Characters output that differ from the label. Unreadable characters are written as ? and do not count as wrong."],
    detected_and_tracked: ["Detected and tracked", "Labelled vehicles found and tracked at the labelled frame. Labels are linked to system vehicles by box position only, so plate scores aren't circular."],
    plate_characters_correct: ["Plate characters read correctly", "Share of labelled plate characters read correctly. The rest are ? (left unread) or wrong."],
    type_compatible: ["Vehicle type compatible", "Type exact, or a compatible class (for example car and SUV)."],
  };
  async function openPerformance() {
    if (!S.overview) return;
    const ev = S.overview.evaluation || {};
    const items = (ev.metrics || []).map((m) => ({ key: m.key, value: m.value, label: (METRIC_INFO[m.key] || [m.label])[0], what: (METRIC_INFO[m.key] || [])[1], detail: m.detail, source: ev.source }));
    const cc = S.overview.crosscam_evaluation;
    if (cc && Number.isFinite(num(cc.groups))) {
      const checkable = num(cc.groups) - (num(cc.not_tracked) || 0);
      items.push({ key: "crosscam", value: cc.correct_links + "/" + checkable, label: "Cross-camera groups linked",
        what: "Labelled groups of the same vehicle across two cameras that the system linked correctly. Groups where a vehicle was never tracked can't be checked.",
        source: "crosscam_evaluation.json", raw: cc });
    }
    $("perf-lede").textContent = "Measured on the team's labelled test clips" + (ev.clip_count ? " · " + ev.clip_count + " clips" : "") + (ev.labelled_vehicles ? ", " + ev.labelled_vehicles + " vehicles" : "") + ".";
    $("metric-list").replaceChildren(...items.map((m) => el("li", null, el("button", { class: "metric", type: "button", "data-k": m.key, onclick: () => selectMetric(m) },
      el("b", { text: m.value }), el("span", null, m.label, el("small", { text: m.detail || "" })), el("span", { class: "f-go", text: "›" })))));
    S.perfItems = items;
    if (items.length) selectMetric(items.find((m) => m.key === S.perfKey) || items[0]);
    else $("metric-list").replaceChildren(el("li", { class: "muted", style: "padding:12px", text: "No evaluation files were found." }));

    try {
      const review = await loadReview();
      const variants = (review.robustness && review.robustness.variants) || {};
      const share = (s) => { const m = /\((\d+)%\)/.exec(String(s || "")); return m ? Number(m[1]) / 100 : NaN; };
      const rows = Object.entries(variants).map(([name, v]) => el("div", { class: "bar-row" },
        el("span", { text: cap(name.replace("down_", "downscale ")) }),
        el("div", { class: "bar" }, el("i", { style: "width:" + (share(v.registered_vehicles_matched_correctly) * 100 || 0) + "%" })),
        el("b", { text: String(v.registered_vehicles_matched_correctly || "—").split(" ")[0] }),
        el("div", { class: "bar fail" }, el("i", { style: "width:" + (share(v.plate_chars_WRONG) * 100 || 0) + "%" })),
        el("b", { text: pct(share(v.plate_chars_WRONG)) })));
      $("robust").replaceChildren(el("div", { class: "bar-row head" }, el("span", { text: "Variant" }), el("span", { text: "Registered matched" }), el("span"), el("span", { text: "Wrong characters" }), el("span")), ...rows);
      $("robust-note").textContent = "Degraded copies of " + ((review.robustness && review.robustness.clips) || []).join(", ") + ". False confident matches stayed at zero in every variant. This sweep ran on an earlier pipeline version and hasn't been re-run since.";
    } catch (_) {
      $("robust").replaceChildren(el("p", { class: "muted", text: "Robustness results aren't available." }));
    }

    try {
      const modelData = await getJSON("/api/colour/model_info");
      const info = modelData.linear_probe_info || {};
      const vm = info.val_metrics || {};
      const tm = info.test_metrics || {};
      const v2 = !!vm.probe_v2;
      const probeV = v2 ? vm.probe_v2 : (vm.probe || {});
      const probeT = v2 ? tm.probe_v2 : (tm.probe || {});
      const cell = (m) => (m && Number.isFinite(num(m.accuracy)) ? pct(m.accuracy, 1) + " · top-2 " + pct(m.top2_accuracy, 1) + " · F1 " + pct(m.macro_f1, 1) : "—");
      const cc = modelData.cctv_transfer && modelData.cctv_transfer.methods;
      const ccCell = (k) => (cc && cc[k] ? cc[k].exact + "/" + modelData.cctv_transfer.n + " exact · " + cc[k].near + " near · " + cc[k].unknown + " unknown" : "—");
      const rows = [
        ["VCoR validation (1,542 crops)", cell(vm.clip_zero_shot), v2 ? cell(vm.probe_v1) : "—", cell(probeV)],
        ["VCoR test (1,545 crops, scored once)", cell(tm.clip_zero_shot), v2 ? cell(tm.probe_v1) : "—", cell(probeT)],
        ["Team CCTV crops (" + (modelData.cctv_transfer ? modelData.cctv_transfer.n : "62") + " vehicles, reporting only)", ccCell("clip_zero_shot"), ccCell("probe_v1"), ccCell("probe_v2")],
      ];
      $("colour-probe-perf").replaceChildren(el("div", null,
        el("p", { class: "muted small", style: "padding:12px 16px 0",
          text: "Production method: " + String(modelData.active_method || "unknown").toUpperCase() + " (config.yaml) · probe file: " + (modelData.linear_probe_file || "none") +
            (info.optimal_C != null ? " · C = " + info.optimal_C + " chosen on validation" : "") + " · backbone " + (info.backbone || "ViT-B-32") + "." }),
        el("table", { class: "cases" },
          el("thead", null, el("tr", null, ...["Data", "CLIP zero-shot (production)", "Probe v1 (shipped)", v2 ? "Probe v2 (retrained)" : "Linear probe"].map((h) => el("th", { text: h })))),
          el("tbody", null, ...rows.map((r) => el("tr", null, el("td", { class: "clip", text: r[0] }), ...r.slice(1).map((t) => el("td", { text: t })))))),
        el("p", { class: "ev-note", style: "padding:0 16px 12px",
          text: "VCoR scores are on clean, tightly cropped photos and do not transfer to CCTV. On the team's CCTV crops zero-shot CLIP is still the most accurate, so it stays the production default. The probe v1 weights were under-fit (every prediction fell below the confidence gate); v2 fixes that on VCoR but not on CCTV. The CCTV crops were never used for training or model selection. Colour is supporting evidence only, never identity." })
      ));
    } catch (_) {
      $("colour-probe-perf").replaceChildren(el("p", { class: "muted", text: "Colour model benchmark diagnostics currently unavailable." }));
    }
  }
  function selectMetric(m) {
    S.perfKey = m.key;
    document.querySelectorAll("#metric-list .metric").forEach((b) => b.setAttribute("aria-current", String(b.dataset.k === m.key)));
    $("perf-evidence").replaceChildren(...[
      evHead("How it's measured", m.label, m.what),
      section("Result", null, kv([["Value", m.value], ["Scope", m.detail]])),
      m.raw ? section("Breakdown", null, kv(Object.entries(m.raw).map(([k, v]) => [cap(k), v]))) : null,
      section("Source", null, el("p", { class: "muted", text: m.source ? "TRACEVISION_DATA/reports/" + m.source : "Not recorded" })),
      el("p", { class: "ev-note", text: "The test set is small and mostly ground-level footage. These figures describe this set, not every CCTV condition." }),
    ].flat().filter(Boolean));
  }

  /* ---------------------------------------------------------------- start */
  initMeta();
  initOfficer();
  initEnfTabs();
  initIntake();
  initPlayer();
  initCrosscam();
  window.addEventListener("hashchange", route);
  route();
  loadOverview();
})();
