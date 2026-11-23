"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const state = {
    overview: null,
    limits: null,
    engineStatus: "starting",
    selectedFile: null,
    previewUrl: null,
    jobId: null,
    jobPollStartedAt: 0,
    jobPollErrors: 0,
    jobPollTimer: null,
    startupPollCount: 0,
    startupPollTimer: null,
    review: null,
    reviewPromise: null,
    reviewRequestId: 0,
    selectedCrosscamPair: null,
    selectedCrosscamTracks: {},
    crosscamPairRequestId: 0,
    crosscamResults: {},
    selectedReportClip: null,
    demoRun: null,
    demoTimer: null,
    demoResultClip: null,
    demoRequestId: 0,
    commandActiveIndex: 0,
    navigationChordPending: false,
    navigationChordTimer: null,
    result: null,
    resultKind: null,
    resultId: null,
    resultFiles: [],
    selectedTrackId: null,
    resultRequestId: 0,
    evidenceFrames: [],
  };

  const fileInput = byId("video-file");
  const dropzone = byId("dropzone");
  const submitButton = byId("submit-job");
  const toast = byId("toast");

  function setText(id, value) {
    const node = byId(id);
    if (node) node.textContent = value == null ? "" : String(value);
  }

  function formatBytes(size) {
    if (!Number.isFinite(size) || size < 0) return "—";
    if (size >= 1024 * 1024 * 1024) return (size / (1024 * 1024 * 1024)).toFixed(1) + " GB";
    if (size >= 1024 * 1024) return Math.round(size / (1024 * 1024)) + " MB";
    if (size >= 1024) return Math.round(size / 1024) + " KB";
    return size + " bytes";
  }

  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toast.classList.remove("is-visible"), 2800);
  }

  function setUploadFeedback(message, kind) {
    const node = byId("upload-feedback");
    if (!node) return;
    node.textContent = message;
    node.dataset.kind = kind || "neutral";
  }

  function updateSubmitState() {
    if (submitButton) submitButton.disabled = !state.selectedFile || state.engineStatus !== "ready";
  }

  function renderEngine(engine) {
    const engineStatus = engine && engine.status ? engine.status : "error";
    state.engineStatus = engineStatus;
    const pill = byId("engine-pill");
    const notice = byId("service-notice");
    const title = byId("service-title");
    const message = byId("service-message");
    const details = byId("service-details");
    const technical = byId("service-error");
    const privacyEngine = byId("privacy-engine");
    if (pill) {
      pill.dataset.state = engineStatus;
      const label = pill.querySelector("span");
      if (label) label.textContent = engineStatus === "ready" ? "Engine ready" : engineStatus === "disabled" ? "Stored results only" : engineStatus === "error" ? "Engine unavailable" : "Engine starting";
    }
    if (privacyEngine) privacyEngine.textContent = engineStatus === "ready" ? "READY" : engineStatus === "disabled" ? "UI-ONLY MODE" : engineStatus === "error" ? "UNAVAILABLE" : "STARTING";
    if (engineStatus === "disabled") {
      // Deliberate UI-only mode (TRACEVISION_UI_ONLY=1): not a fault, but live analysis must not look available.
      notice.hidden = false;
      notice.className = "notice notice-wait";
      title.textContent = "Live analysis is off on this machine";
      message.textContent = (engine && engine.message ? engine.message + " " : "") +
        "Every result shown here was produced earlier by the full pipeline and is read from runs/.";
      details.hidden = true;
      setUploadFeedback("Uploads are disabled in UI-only mode. Open a stored result below.", "wait");
    } else if (engineStatus === "ready") {
      notice.hidden = true;
      setUploadFeedback(state.selectedFile ? "Ready to submit to the local engine." : "Choose a video file. Analysis begins only after you submit it.");
    } else if (engineStatus === "starting") {
      notice.hidden = false;
      notice.className = "notice notice-wait";
      title.textContent = "Analysis engine is starting";
      message.textContent = "Uploads stay disabled until the local engine is ready. This check will stop after 30 seconds.";
      details.hidden = true;
      setUploadFeedback("Waiting for the local engine to finish startup.", "wait");
    } else {
      notice.hidden = false;
      notice.className = "notice notice-error";
      title.textContent = engineStatus === "offline" ? "Local service unavailable" : "Analysis engine unavailable";
      message.textContent = engineStatus === "offline"
        ? "The page cannot reach the local API. Retry the connection or restart the app. Stored results are still available when the API is running."
        : "The engine did not start. Uploads are disabled; stored analyses below remain available.";
      const raw = engine && engine.error ? String(engine.error) : "";
      details.hidden = !raw;
      technical.textContent = raw;
      setUploadFeedback("Analysis is unavailable. You can still open stored results.", "error");
    }
    const aboutStatus = byId("about-engine-status");
    if (aboutStatus) {
      const summary = engineStatus === "ready" ? "The local analysis engine is ready."
        : engineStatus === "disabled" ? "Live analysis is disabled (UI-only mode); stored results are reviewed read-only."
        : engineStatus === "starting" ? "The local analysis engine is starting."
          : "The local analysis engine is unavailable. Stored-result review and demo rehearsal remain available.";
      aboutStatus.textContent = summary + (engine && engine.error ? " Detail: " + String(engine.error) : "");
    }
    updateSubmitState();
  }

  function metricExplanation(key, label) {
    const descriptions = {
      registered_matches: "Registered vehicles with a correct top-ranked registry record, divided by labelled registered vehicles.",
      false_confident_matches: "Unregistered labelled vehicles that received a confident registry match. Lower is safer.",
      wrong_plate_characters: "Known ground-truth plate characters read incorrectly. Unknown characters shown as ? are counted separately.",
      detected_and_tracked: "Labelled vehicles that the pipeline detected and tracked at the labelled frame.",
      crosscam_correct_links: "Cross-camera reference groups with a correct system link. This is group-level evaluation data.",
      plate_characters_correct: "Known ground-truth plate characters read correctly. The rest are ? (unread) or wrong; wrong is reported separately.",
      type_compatible: "Detected labelled vehicles whose type is the same or compatible (for example car and SUV).",
    };
    return descriptions[key] || (label ? "Reported metric from the local evaluation files: " + label + "." : "Metric definition is not available in the local report.");
  }

  function renderEvaluation(evaluation, crosscam) {
    const grid = byId("metric-grid");
    const metrics = evaluation && Array.isArray(evaluation.metrics) ? evaluation.metrics.slice() : [];
    if (crosscam && Number.isFinite(crosscam.groups) && crosscam.groups > 0) {
      metrics.push({
        key: "crosscam_correct_links",
        label: "Cross-camera correct links",
        value: crosscam.correct_links + "/" + crosscam.groups,
        detail: String(crosscam.wrong_links_on_groups) + " wrong links in the evaluation",
      });
    }
    if (grid) {
      grid.replaceChildren();
      if (metrics.length === 0) {
        const empty = document.createElement("article");
        empty.className = "metric-card panel metric-empty";
        empty.textContent = "No evaluation figures were found in the local reports.";
        grid.appendChild(empty);
      }
      metrics.forEach((metric) => {
        const card = document.createElement("article");
        card.className = "metric-card panel";
        const metricLabel = metric.label || metric.key || "Evaluation metric";
        card.title = metricExplanation(metric.key, metricLabel);
        card.tabIndex = 0;
        card.setAttribute("aria-label", metricLabel + ": " + String(metric.value == null ? "not reported" : metric.value) + ". " + card.title);
        const label = document.createElement("span");
        label.textContent = metricLabel;
        const value = document.createElement("b");
        value.textContent = metric.value == null || metric.value === "" ? "—" : String(metric.value);
        const note = document.createElement("small");
        note.textContent = metric.detail || ((evaluation && evaluation.clip_count ? evaluation.clip_count + "-clip evaluation" : "Local evaluation report"));
        card.append(label, value, note);
        grid.appendChild(card);
      });
    }
    const source = evaluation && evaluation.source ? evaluation.source : "local evaluation files";
    const clipText = evaluation && evaluation.clip_count ? " · " + evaluation.clip_count + " clips" : "";
    setText("evaluation-source", source + clipText);
    setText("evaluation-note", metrics.length
      ? "Reported evaluation figures are loaded at runtime from local report files; they are not computed or altered by the interface."
      : "Evaluation data is missing or not in a recognised report format. No figures are substituted.");
  }

  function formatCameraType(cameraType) {
    return String(cameraType || "unknown").replace(/_/g, " ").toUpperCase();
  }

  function renderSamples(clips) {
    const grid = byId("sample-grid");
    const empty = byId("samples-empty");
    if (!grid) return;
    grid.replaceChildren();
    const list = Array.isArray(clips) ? clips : [];
    setText("sample-count", list.length + (list.length === 1 ? " stored result" : " stored results"));
    if (empty) empty.hidden = list.length > 0;
    list.forEach((clip) => {
      const card = document.createElement("article");
      card.className = "sample-card panel";
      const art = document.createElement("div");
      art.className = "sample-art";
      art.setAttribute("aria-hidden", "true");
      const frame = document.createElement("div");
      frame.className = "sample-art-frame";
      const artId = document.createElement("span");
      artId.className = "sample-art-id";
      artId.textContent = "STORED EVIDENCE / " + clip.clip_id;
      const camera = document.createElement("span");
      camera.className = "sample-camera";
      camera.textContent = formatCameraType(clip.camera_type);
      art.append(frame, artId, camera);

      const body = document.createElement("div");
      body.className = "sample-body";
      const titleRow = document.createElement("div");
      titleRow.className = "sample-title-row";
      const title = document.createElement("h3");
      title.textContent = clip.clip_id;
      const stored = document.createElement("span");
      stored.className = "sample-stored";
      stored.textContent = "STORED RESULT";
      titleRow.append(title, stored);

      const data = document.createElement("div");
      data.className = "sample-data";
      [
        ["VEHICLES", clip.vehicle_count],
        ["MATCH", clip.match_count],
        ["NO CONFIDENT MATCH", clip.no_match_count],
      ].forEach((item) => {
        const entry = document.createElement("span");
        entry.append(document.createTextNode(item[0]));
        const value = document.createElement("b");
        value.textContent = item[1] == null ? "—" : String(item[1]);
        entry.appendChild(value);
        data.appendChild(entry);
      });

      const open = document.createElement("a");
      open.className = "sample-open";
      if (clip.has_video) {
        open.href = "/#results/runs/" + encodeURIComponent(clip.clip_id);
        open.innerHTML = "Open stored result <span aria-hidden=\"true\">↗</span>";
      } else if (clip.has_report) {
        open.href = "/runs/" + encodeURIComponent(clip.clip_id) + "/report";
        open.innerHTML = "Open stored report <span aria-hidden=\"true\">↗</span>";
      } else {
        open.href = "#samples-title";
        open.setAttribute("aria-disabled", "true");
        open.textContent = "Stored media unavailable";
      }
      open.setAttribute("aria-label", "Open stored analysis for " + clip.clip_id);
      body.append(titleRow, data, open);
      card.append(art, body);
      grid.appendChild(card);
    });
  }

  // Totals over the stored results returned by /api/overview (runs/clip*/result.json). Nothing is estimated: a value
  // missing from every clip is shown as unavailable rather than zero.
  function renderOperations(data) {
    const strip = byId("ops-strip");
    if (!strip) return;
    strip.replaceChildren();
    const clips = data && Array.isArray(data.clips) ? data.clips : [];
    if (!clips.length) {
      const empty = document.createElement("div");
      empty.className = "ops-empty";
      empty.textContent = "No stored results were found in runs/.";
      strip.appendChild(empty);
      setText("ops-source", "runs/ · no results");
      return;
    }
    const sum = (key) => {
      const values = clips.map((clip) => clip[key]).filter((value) => Number.isFinite(Number(value)) && value !== null && value !== "");
      return values.length ? values.reduce((total, value) => total + Number(value), 0) : null;
    };
    const crosscam = data.crosscam_evaluation;
    const withVideo = clips.filter((clip) => clip.has_video).length;
    const items = [
      { label: "Clips analysed", value: clips.length, note: withVideo + " with video on this machine" },
      { label: "Vehicles tracked", value: sum("vehicle_count"), note: "after track re-linking" },
      { label: "Plates read", value: sum("plates_read"), note: "fused from several frames" },
      { label: "Registry matches", value: sum("match_count"), note: "confident decisions", tone: "good" },
      { label: "Ambiguous", value: sum("ambiguous_count"), note: "top two too close", tone: "warn" },
      { label: "No confident match", value: sum("no_match_count"), note: "system abstained", tone: "muted" },
      { label: "Cross-camera links", value: crosscam && Number.isFinite(Number(crosscam.system_links_total)) ? crosscam.system_links_total : null,
        note: crosscam ? crosscam.correct_links + "/" + crosscam.groups + " reference groups correct" : "no pair evaluation found", tone: "link" },
    ];
    items.forEach((item) => {
      const cell = document.createElement("div");
      cell.className = "ops-cell" + (item.tone ? " tone-" + item.tone : "");
      const label = document.createElement("span");
      label.textContent = item.label;
      const value = document.createElement("b");
      value.textContent = item.value === null || item.value === undefined ? "—" : String(item.value);
      const note = document.createElement("small");
      note.textContent = item.value === null || item.value === undefined ? "not recorded" : item.note;
      cell.append(label, value, note);
      strip.appendChild(cell);
    });
    const latest = clips.map((clip) => clip.processed_at).filter(Boolean).sort().pop();
    setText("ops-source", "runs/ · " + clips.length + " result files" + (latest ? " · latest " + String(latest).replace("T", " ") : ""));
  }

  function applyOverview(data) {
    state.overview = data;
    renderOperations(data);
    state.limits = data.limits || null;
    if (state.limits) {
      const allowed = Array.isArray(state.limits.allowed_extensions) ? state.limits.allowed_extensions : [];
      const accept = allowed.join(",");
      fileInput.setAttribute("accept", accept);
      const pretty = allowed.map((extension) => extension.replace(/^\./, "").toUpperCase()).join(", ");
      const maxLabel = formatBytes(Number(state.limits.max_bytes));
      setText("file-rules", pretty + " · up to " + maxLabel);
      setText("limit-label", maxLabel);
    }
    renderEngine(data.engine || { status: "error", error: "The API did not return engine state." });
    renderEvaluation(data.evaluation, data.crosscam_evaluation);
    renderSamples(data.clips);
    populateDemoClips(data.clips);
    if (byId("command-dialog").open) renderCommandList(byId("command-search").value);
  }

  async function refreshOverview(autoPoll) {
    try {
      const response = await fetch("/api/overview", { cache: "no-store" });
      if (!response.ok) throw new Error("The local API returned HTTP " + response.status + ". Restart the app to load the current status endpoint.");
      const data = await response.json();
      applyOverview(data);
      if (state.engineStatus === "starting") {
        if (!autoPoll) state.startupPollCount = 0;
        if (state.startupPollCount < 15) {
          state.startupPollCount += 1;
          window.clearTimeout(state.startupPollTimer);
          state.startupPollTimer = window.setTimeout(() => refreshOverview(true), 2000);
        } else {
          setText("service-message", "Engine startup is taking longer than expected. Automatic checks have stopped; use Retry to check again.");
        }
      } else {
        state.startupPollCount = 0;
        window.clearTimeout(state.startupPollTimer);
      }
      return data;
    } catch (error) {
      renderEngine({ status: "offline", error: error && error.message ? error.message : String(error) });
      renderOperations(null);
      setText("ops-source", "Local API unavailable");
      setText("evaluation-source", "Local API unavailable");
      setText("evaluation-note", "Stored evaluation figures could not be loaded from the local service.");
      const grid = byId("metric-grid");
      if (grid) {
        const empty = document.createElement("article");
        empty.className = "metric-card panel metric-empty";
        empty.textContent = "Could not load evaluation files.";
        grid.replaceChildren(empty);
      }
      renderSamples([]);
      return null;
    }
  }

  function validateFile(file) {
    if (!file) return "Choose a video file first.";
    if (!state.limits) return "The local file rules have not loaded yet. Retry the local service check.";
    const allowed = Array.isArray(state.limits.allowed_extensions) ? state.limits.allowed_extensions : [];
    const lowerName = file.name.toLowerCase();
    if (!allowed.some((extension) => lowerName.endsWith(extension.toLowerCase()))) {
      return "This file type is not supported. Allowed formats: " + allowed.join(", ") + ".";
    }
    if (Number.isFinite(Number(state.limits.max_bytes)) && file.size > Number(state.limits.max_bytes)) {
      return "This file is larger than the local limit of " + formatBytes(Number(state.limits.max_bytes)) + ".";
    }
    if (file.size === 0) return "This file is empty.";
    return "";
  }

  function clearSelectedFile() {
    state.selectedFile = null;
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = null;
    fileInput.value = "";
    byId("selected-file").hidden = true;
    byId("dropzone").hidden = false;
    byId("video-preview").removeAttribute("src");
    byId("video-preview").load();
    setText("file-name", "");
    setText("file-size", "");
    setUploadFeedback(state.engineStatus === "ready" ? "Choose a video file. Analysis begins only after you submit it." : "Analysis is unavailable. You can still open stored results.");
    updateSubmitState();
  }

  function selectFile(file) {
    const problem = validateFile(file);
    if (problem) {
      setUploadFeedback(problem, "error");
      showToast(problem);
      return;
    }
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.selectedFile = file;
    state.previewUrl = URL.createObjectURL(file);
    byId("video-preview").src = state.previewUrl;
    byId("selected-file").hidden = false;
    byId("dropzone").hidden = true;
    setText("file-name", file.name);
    setText("file-size", formatBytes(file.size));
    setUploadFeedback(state.engineStatus === "ready" ? "Ready to submit to the local engine." : "Preview ready. The engine must be available before upload.");
    updateSubmitState();
  }

  function bindUploadControls() {
    dropzone.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      fileInput.click();
    });
    dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        fileInput.click();
      }
    });
    fileInput.addEventListener("change", () => selectFile(fileInput.files && fileInput.files[0]));
    byId("remove-file").addEventListener("click", clearSelectedFile);
    ["dragenter", "dragover"].forEach((type) => dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragging");
    }));
    ["dragleave", "drop"].forEach((type) => dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.remove("is-dragging");
    }));
    dropzone.addEventListener("drop", (event) => {
      const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
      if (file) selectFile(file);
    });
    submitButton.addEventListener("click", submitJob);
    byId("refresh-overview").addEventListener("click", refreshWorkspaceData);
    byId("retry-overview").addEventListener("click", refreshWorkspaceData);
    byId("retry-job-status").addEventListener("click", () => {
      state.jobPollErrors = 0;
      state.jobPollStartedAt = Date.now();
      pollJobStatus();
    });
  }

  async function refreshWorkspaceData() {
    state.review = null;
    state.reviewPromise = null;
    await refreshOverview(false);
    handleHashRoute();
  }

  async function submitJob() {
    if (!state.selectedFile) {
      setUploadFeedback("Choose a video file first.", "error");
      return;
    }
    if (state.engineStatus !== "ready") {
      setUploadFeedback("The local analysis engine is unavailable. Stored results remain accessible.", "error");
      return;
    }
    const form = new FormData();
    form.append("video", state.selectedFile);
    submitButton.disabled = true;
    setUploadFeedback("Uploading to the local analysis service…");
    try {
      const response = await fetch("/jobs", { method: "POST", body: form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Upload failed with HTTP " + response.status + ".");
      if (!data.job_id) throw new Error("The local service did not return a job id.");
      state.jobId = String(data.job_id);
      state.jobPollErrors = 0;
      state.jobPollStartedAt = Date.now();
      showProcessing();
      setText("processing-title", "Analysis in progress");
      setText("processing-subtitle", "The local service accepted this clip.");
      setJobStatus({ status: "queued", phase: "queued", position: 1 });
      clearSelectedFile();
      pollJobStatus();
    } catch (error) {
      setUploadFeedback(error && error.message ? error.message : "Upload could not be started.", "error");
      if (error && /engine could not start/i.test(error.message || "")) renderEngine({ status: "error", error: error.message });
      updateSubmitState();
    }
  }

  function showProcessing() {
    const panel = byId("processing-panel");
    panel.hidden = false;
    panel.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    byId("job-error").hidden = true;
    byId("job-result-links").hidden = true;
    byId("retry-job-status").hidden = true;
  }

  function setJobStatus(job) {
    const status = job.status || "running";
    const phase = job.phase || (status === "running" ? "analysis" : status);
    const pill = byId("job-status-pill");
    pill.dataset.state = status === "done" ? "complete" : status;
    pill.textContent = status === "done" ? "COMPLETE" : status.toUpperCase();
    const steps = Array.from(document.querySelectorAll(".job-step"));
    const order = ["queued", "analysis", "report", "complete"];
    let current = status === "done" ? "complete" : status === "queued" ? "queued" : phase === "report" ? "report" : "analysis";
    if (status === "error") current = job.failed_at === "report" ? "report" : job.failed_at === "startup" ? "queued" : "analysis";
    const currentIndex = order.indexOf(current);
    steps.forEach((step) => {
      const stepName = step.dataset.step;
      const index = order.indexOf(stepName);
      step.classList.toggle("is-complete", status === "done" || (status !== "error" && index < currentIndex));
      step.classList.toggle("is-active", status !== "done" && status !== "error" && index === currentIndex);
      step.classList.toggle("is-error", status === "error" && index === currentIndex);
    });
    if (status === "queued") {
      setText("processing-title", "Queued for analysis");
      setText("processing-subtitle", "Queue position " + (job.position || 1) + ". Waiting for the local worker.");
    } else if (status === "running" && phase === "report") {
      setText("processing-title", "Building the evidence report");
      setText("processing-subtitle", "The analysis pipeline finished; the report is being written.");
    } else if (status === "running") {
      const elapsed = Number.isFinite(job.elapsed_s) ? " · " + Math.round(job.elapsed_s) + " s elapsed" : "";
      setText("processing-title", "Analysis running");
      setText("processing-subtitle", "The engine is processing the clip." + elapsed);
    } else if (status === "done") {
      const count = job.summary && Number.isFinite(job.summary.vehicles_after_relink) ? job.summary.vehicles_after_relink : null;
      setText("processing-title", "Analysis complete");
      setText("processing-subtitle", "The job and report completed" + (count == null ? "." : " · " + count + " vehicles in the result."));
      renderJobLinks(state.jobId);
    } else if (status === "error") {
      setText("processing-title", "Analysis stopped");
      setText("processing-subtitle", "The job failed. No completed result is available for this upload.");
      const error = byId("job-error");
      error.textContent = job.error || "The local service reported an error without details.";
      error.hidden = false;
    }
  }

  function renderJobLinks(jobId) {
    const links = byId("job-result-links");
    links.replaceChildren();
    const safeId = encodeURIComponent(jobId);
    [
      ["Open results dashboard", "/#results/jobs/" + safeId],
      ["Open HTML report", "/jobs/" + safeId + "/report"],
      ["Download PDF", "/jobs/" + safeId + "/report.pdf"],
      ["View result JSON", "/jobs/" + safeId + "/result"],
    ].forEach((item) => {
      const anchor = document.createElement("a");
      anchor.href = item[1];
      anchor.textContent = item[0];
      links.appendChild(anchor);
    });
    links.hidden = false;
  }

  async function pollJobStatus() {
    if (!state.jobId) return;
    if (Date.now() - state.jobPollStartedAt > 10 * 60 * 1000) {
      setText("processing-subtitle", "Status checks paused after 10 minutes. The job may still be running; retry when ready.");
      byId("retry-job-status").hidden = false;
      return;
    }
    try {
      const response = await fetch("/jobs/" + encodeURIComponent(state.jobId), { cache: "no-store" });
      if (!response.ok) throw new Error("The job status endpoint returned HTTP " + response.status + ".");
      const job = await response.json();
      state.jobPollErrors = 0;
      byId("retry-job-status").hidden = true;
      setJobStatus(job);
      if (job.status === "done" || job.status === "error") return;
    } catch (error) {
      state.jobPollErrors += 1;
      setText("processing-subtitle", error && error.message ? error.message : "Could not read job status.");
      if (state.jobPollErrors >= 3) {
        byId("retry-job-status").hidden = false;
        return;
      }
    }
    window.clearTimeout(state.jobPollTimer);
    state.jobPollTimer = window.setTimeout(pollJobStatus, 1500);
  }

  function resultPathFromHash() {
    const parts = window.location.hash.replace(/^#\/?/, "").split("/");
    if (parts[0] !== "results" || parts.length !== 3) return null;
    const kind = parts[1];
    let id;
    try { id = decodeURIComponent(parts[2]); } catch (_) { return null; }
    if (kind === "runs" && /^clip\d+$/.test(id)) return { kind: kind, id: id };
    if (kind === "jobs" && /^[0-9a-f]{12}$/i.test(id)) return { kind: kind, id: id };
    return null;
  }

  function demoPathFromHash() {
    const parts = window.location.hash.replace(/^#\/?/, "").split("/");
    if (parts[0] !== "demo" || parts.length !== 2 || !/^clip\d+$/.test(parts[1])) return null;
    return { clipId: parts[1] };
  }

  function showLanding() {
    window.clearTimeout(state.demoTimer);
    state.demoTimer = null;
    state.demoRun = null;
    state.demoResultClip = null;
    const video = byId("result-video");
    if (video) {
      video.pause();
      video.removeAttribute("src");
      video.load();
    }
    byId("landing-view").hidden = false;
    byId("results-view").hidden = true;
    byId("demo-view").hidden = true;
    ["crosscam-view", "reports-view", "insights-view"].forEach((id) => { byId(id).hidden = true; });
    ["pair-video-a", "pair-video-b"].forEach((id) => {
      const pairVideo = byId(id);
      if (pairVideo) pairVideo.pause();
    });
    state.result = null;
    state.resultKind = null;
    state.resultId = null;
    state.resultFiles = [];
    state.selectedTrackId = null;
    document.title = "TRACEVISION AI — Vehicle Traceability";
    setText("breadcrumb-current", "Overview");
    const hash = window.location.hash.replace(/^#\/?/, "");
    setActiveNav(hash === "upload" ? "upload" : hash === "samples-title" ? "results" : "overview");
  }

  function setActiveNav(view) {
    document.querySelectorAll(".nav-link[data-nav-view]").forEach((link) => {
      const active = link.dataset.navView === view;
      link.classList.toggle("is-active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function showSecondaryShell(view) {
    window.clearTimeout(state.demoTimer);
    state.demoTimer = null;
    state.demoRun = null;
    byId("landing-view").hidden = true;
    byId("results-view").hidden = true;
    byId("demo-view").hidden = true;
    ["crosscam-view", "reports-view", "insights-view"].forEach((id) => { byId(id).hidden = id !== view + "-view"; });
    const video = byId("result-video");
    if (video) video.pause();
    ["pair-video-a", "pair-video-b"].forEach((id) => { byId(id).pause(); });
    setActiveNav(view);
    const titles = { crosscam: "Cross-camera trace", reports: "Investigation reports", insights: "Measured performance" };
    document.title = "TRACEVISION AI — " + (titles[view] || "Review");
    setText("breadcrumb-current", titles[view] || "Review");
  }

  function showResultsShell(route) {
    window.clearTimeout(state.demoTimer);
    state.demoTimer = null;
    state.demoRun = null;
    byId("landing-view").hidden = true;
    byId("results-view").hidden = false;
    byId("demo-view").hidden = true;
    ["crosscam-view", "reports-view", "insights-view"].forEach((id) => { byId(id).hidden = true; });
    setActiveNav("results");
    byId("results-loading").hidden = false;
    byId("results-content").hidden = true;
    byId("results-error").hidden = true;
    byId("vehicle-detail").hidden = true;
    setText("result-title", route.kind === "runs" ? route.id : "Uploaded analysis");
    setText("result-meta", "Loading stored analysis data…");
    byId("demo-result-banner").hidden = !(state.demoResultClip && route.kind === "runs" && state.demoResultClip === route.id);
    setText("breadcrumb-current", "Results");
    const html = byId("result-html-report");
    const pdf = byId("result-pdf-report");
    html.href = route.kind === "runs" ? "/runs/" + encodeURIComponent(route.id) + "/report" : "/jobs/" + encodeURIComponent(route.id) + "/report";
    pdf.href = route.kind === "runs" ? "/runs/" + encodeURIComponent(route.id) + "/report.pdf" : "/jobs/" + encodeURIComponent(route.id) + "/report.pdf";
    html.hidden = false;
    pdf.hidden = false;
    document.title = "TRACEVISION AI — Results";
  }

  async function openResult(route, requestId) {
    const base = "/data/" + route.kind + "/" + encodeURIComponent(route.id);
    try {
      const resultResponse = await fetch(base + "/result.json", { cache: "no-store" });
      if (!resultResponse.ok) throw new Error("Result data could not be loaded (HTTP " + resultResponse.status + ").");
      const result = await resultResponse.json();
      let files = [];
      try {
        const fileResponse = await fetch(base + "/files", { cache: "no-store" });
        if (fileResponse.ok) {
          const listed = await fileResponse.json();
          if (Array.isArray(listed)) files = listed.filter((name) => typeof name === "string" && /^t\d+_(plate|vehicle)_f\d+\.jpg$/.test(name));
        }
      } catch (_) { files = []; }
      if (requestId !== state.resultRequestId) return;
      state.result = result;
      state.resultKind = route.kind;
      state.resultId = route.id;
      state.resultFiles = files;
      state.selectedTrackId = null;
      renderResult(result, route);
    } catch (error) {
      if (requestId !== state.resultRequestId) return;
      byId("results-loading").hidden = true;
      const failure = byId("results-error");
      failure.textContent = error && error.message ? error.message : "Result could not be loaded.";
      failure.hidden = false;
    }
  }

  function handleHashRoute() {
    const route = resultPathFromHash();
    if (route) {
      const requestId = ++state.resultRequestId;
      showResultsShell(route);
      openResult(route, requestId);
      return;
    }
    const demoRoute = demoPathFromHash();
    if (demoRoute) {
      state.resultRequestId += 1;
      showDemoView(demoRoute.clipId);
      return;
    }
    const view = window.location.hash.replace(/^#\/?/, "").split("/")[0];
    if (["crosscam", "reports", "insights"].includes(view)) {
      state.resultRequestId += 1;
      showSecondaryShell(view);
      loadReviewView(view);
      return;
    }
    state.resultRequestId += 1;
    showLanding();
  }

  function formatTime(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return "00:00";
    const whole = Math.floor(seconds);
    const minutes = Math.floor(whole / 60);
    const remainder = whole % 60;
    return String(minutes).padStart(2, "0") + ":" + String(remainder).padStart(2, "0");
  }

  function resultFrameCount(result) {
    return Number(result && result.video && result.video.frames) || 0;
  }

  function resultFps(result) {
    return Number(result && result.video && result.video.fps) || 30;
  }

  function renderResult(result, route) {
    const clipId = String(result.clip_id || route.id);
    const videoMeta = result.video || {};
    const vehicles = Array.isArray(result.vehicles) ? result.vehicles : [];
    const timestamp = result.processed_at ? " · Processed " + String(result.processed_at) : "";
    const camera = result.camera_type ? formatCameraType(result.camera_type) : "CAMERA TYPE UNKNOWN";
    setText("result-title", clipId);
    byId("demo-result-banner").hidden = !(state.demoResultClip && route.kind === "runs" && state.demoResultClip === clipId);
    setText("result-meta", camera + " · " + vehicles.length + (vehicles.length === 1 ? " tracked vehicle" : " tracked vehicles") + timestamp);
    setText("vehicle-count", String(vehicles.length));
    byId("results-loading").hidden = true;
    byId("results-error").hidden = true;
    byId("results-content").hidden = false;
    byId("vehicle-detail").hidden = true;
    byId("vehicle-list-empty").hidden = vehicles.length > 0;

    const video = byId("result-video");
    video.pause();
    video.removeAttribute("src");
    video.load();
    byId("video-unavailable").hidden = true;
    video.src = "/data/" + route.kind + "/" + encodeURIComponent(route.id) + "/video";
    video.load();
    video.onloadedmetadata = () => {
      sizeVideoOverlay();
      updateVideoUI();
      drawTracks();
    };
    const setPlaybackEnabled = (enabled) => {
      ["play-toggle", "seek-back", "seek-forward", "previous-evidence", "next-evidence", "playback-speed", "seek-slider"].forEach((id) => {
        const control = byId(id);
        if (control) control.disabled = !enabled;
      });
    };
    setPlaybackEnabled(true);
    video.onerror = () => {
      byId("video-unavailable").hidden = false;
      byId("track-canvas").hidden = true;
      setPlaybackEnabled(false);
    };
    video.oncanplay = () => {
      byId("video-unavailable").hidden = true;
      byId("track-canvas").hidden = false;
      setPlaybackEnabled(true);
      sizeVideoOverlay();
    };
    renderVehicleList(vehicles);
    buildTimelineMarkers(vehicles, resultFrameCount(result));
    updateVideoUI();
    if (vehicles.length) selectVehicle(vehicles[0].track_id);
    else byId("vehicle-detail").hidden = true;
    setText("viewer-frame", "FRAME 0 / " + (resultFrameCount(result) ? String(resultFrameCount(result) - 1) : "—"));
  }

  function decisionLabel(decision) {
    if (decision === "match") return "MATCH";
    if (decision === "ambiguous") return "AMBIGUOUS";
    if (decision === "no_confident_match") return "NO CONFIDENT MATCH";
    // crosscam.py link_pair: plate evidence reached through a probable (not plate-confirmed) link -> never a match
    if (decision === "candidate_via_probable_link") return "CANDIDATE ONLY (PROBABLE LINK, NOT A MATCH)";
    return String(decision || "DECISION UNKNOWN").replace(/_/g, " ").toUpperCase();
  }

  function decisionClass(decision) {
    if (decision === "match") return "match";
    if (decision === "ambiguous" || decision === "candidate_via_probable_link") return "uncertain";
    if (decision === "no_confident_match") return "no-match";
    return "neutral";
  }

  function renderVehicleList(vehicles) {
    const list = byId("vehicle-list");
    list.replaceChildren();
    vehicles.forEach((vehicle) => {
      const button = document.createElement("button");
      button.className = "vehicle-row";
      button.type = "button";
      button.dataset.trackId = String(vehicle.track_id);
      button.setAttribute("aria-pressed", "false");
      const index = document.createElement("span");
      index.className = "track-index";
      index.textContent = "T" + vehicle.track_id;
      const body = document.createElement("span");
      body.className = "vehicle-row-copy";
      const title = document.createElement("b");
      title.textContent = vehicle.plate && vehicle.plate.fused ? vehicle.plate.fused : (vehicle.type && vehicle.type.label ? vehicle.type.label : "Vehicle");
      const sub = document.createElement("small");
      sub.textContent = (vehicle.type && vehicle.type.label ? vehicle.type.label : "Type unavailable") + " · " + decisionLabel(vehicle.decision);
      body.append(title, sub);
      const stateDot = document.createElement("i");
      stateDot.className = "row-status " + decisionClass(vehicle.decision);
      stateDot.setAttribute("aria-hidden", "true");
      button.append(index, body, stateDot);
      button.addEventListener("click", () => selectVehicle(vehicle.track_id));
      list.appendChild(button);
    });
  }

  function percent(value) {
    if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) return "—";
    return (Math.max(0, Math.min(1, Number(value))) * 100).toFixed(1) + "%";
  }

  function setScore(valueId, meterId, value, max, suffix) {
    if (value === null || value === undefined || value === "") value = NaN;
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      setText(valueId, "—");
      byId(meterId).style.width = "0%";
      return;
    }
    const bounded = Math.max(0, Math.min(max, numeric));
    const shown = max === 1 ? (bounded * 100).toFixed(1) + "%" : bounded.toFixed(1) + (suffix || " / 100");
    setText(valueId, shown);
    byId(meterId).style.width = (bounded / max * 100) + "%";
  }

  function scoreConfidence(positions) {
    if (!Array.isArray(positions)) return null;
    const known = positions.filter((position) => position && position.char !== "?" && position.confidence !== null && position.confidence !== undefined && position.confidence !== "" && Number.isFinite(Number(position.confidence)));
    if (!known.length) return null;
    return known.reduce((total, position) => total + Number(position.confidence), 0) / known.length;
  }

  function swatchColor(label) {
    const colors = {
      white: "#edece4", black: "#252832", silver: "#b7becb", grey: "#858b96",
      gray: "#858b96", red: "#c95d65", blue: "#567cb5", green: "#4f9a76",
      yellow: "#d0b858", brown: "#987358", orange: "#d58346", other: "#9096a4",
      unknown: "#596273",
    };
    return colors[String(label || "").toLowerCase()] || colors.unknown;
  }

  function renderDecision(vehicle) {
    const badge = byId("decision-badge");
    const decision = vehicle.decision;
    badge.className = "decision-badge " + decisionClass(decision);
    badge.textContent = decisionLabel(decision);
    const note = byId("no-match-note");
    if (decision === "no_confident_match" || decision === "ambiguous") {
      note.className = "no-match-note " + decisionClass(decision);
      note.textContent = (decision === "ambiguous" ? "Ambiguous candidate ranking. " : "No confident match. ") +
        (vehicle.decision_reason || "The result does not support a confident registry match.");
      note.hidden = false;
    } else {
      note.hidden = true;
      note.textContent = "";
    }
  }

  // "Why this decision": the stored thresholds (result.config.match) next to the stored values for this vehicle, in
  // the order the matcher applies them. See assets/explain.js; nothing is re-scored here.
  function renderDecisionLogic(vehicle) {
    const list = byId("decision-checks");
    const note = byId("decision-logic-note");
    if (!list || !note) return;
    list.replaceChildren();
    const matchConfig = state.result && state.result.config ? state.result.config.match : null;
    if (!window.TVExplain || !matchConfig) {
      note.textContent = "Decision thresholds were not stored with this result, so the rule cannot be shown. The recorded reason is: " +
        (vehicle.decision_reason || "not recorded") + ".";
      return;
    }
    const logic = window.TVExplain.decisionChecks(vehicle, matchConfig);
    logic.checks.forEach((check) => {
      const item = document.createElement("li");
      const status = !check.reached ? "skipped" : check.pass === true ? "pass" : check.pass === false ? "fail" : "unknown";
      item.className = "decision-check is-" + status + (check.id === logic.decidingCheck ? " is-deciding" : "");
      const mark = document.createElement("i");
      mark.setAttribute("aria-hidden", "true");
      mark.textContent = status === "pass" ? "✓" : status === "fail" ? "✕" : "–";
      const label = document.createElement("span");
      label.textContent = check.label;
      const observed = document.createElement("b");
      observed.textContent = check.observed === null || check.observed === undefined ? "—"
        : check.id === "readable" ? check.observed + " of " + logic.plateLength
          : String(check.observed);
      const threshold = document.createElement("small");
      threshold.textContent = !check.reached ? "not evaluated: decided earlier" : "needs " + check.threshold + (check.note ? " · " + check.note : "");
      item.append(mark, label, observed, threshold);
      item.setAttribute("aria-label", check.label + ": " + observed.textContent + ", " + threshold.textContent + ", " + status);
      list.appendChild(item);
    });
    const outcome = decisionLabel(vehicle.decision);
    if (logic.consistent === false) {
      note.className = "decision-logic-note is-warning";
      note.textContent = "The stored decision (" + outcome + ") is shown unchanged; it does not follow from these values alone. Recorded reason: " +
        (vehicle.decision_reason || "not recorded") + ".";
    } else {
      note.className = "decision-logic-note";
      note.textContent = "Outcome: " + outcome + ". " + (vehicle.decision_reason ? "Recorded reason: " + vehicle.decision_reason + "." : "") +
        " Match score = weighted plate, colour and type agreement (0–100); it ranks candidates and is not a probability.";
    }
  }

  function addCharacterCell(container, character, confidence, index, source) {
    const cell = document.createElement("span");
    const unknown = character === "?";
    const hasConfidence = confidence !== null && confidence !== undefined && confidence !== "" && Number.isFinite(Number(confidence));
    cell.className = "character-cell" + (unknown ? " is-unknown" : "");
    const char = document.createElement("b");
    char.textContent = character;
    const value = document.createElement("small");
    value.textContent = unknown ? "?" : hasConfidence ? percent(confidence) : "—";
    const caption = document.createElement("em");
    caption.textContent = String(index);
    cell.title = unknown
      ? "Character " + index + " is unreadable and remains ?"
      : (source || "OCR character") + " · character " + index + (hasConfidence ? " · confidence " + percent(confidence) : "");
    cell.append(char, value, caption);
    container.appendChild(cell);
  }

  function renderPlate(plate) {
    const cells = byId("plate-cells");
    cells.replaceChildren();
    const status = plate && plate.status ? String(plate.status) : "Plate status not recorded.";
    setText("plate-status", plate && plate.fused ? "Fused read: " + status : "No fused plate read: " + status);
    const fused = plate && typeof plate.fused === "string" ? plate.fused : "";
    const positions = Array.isArray(plate && plate.positions) ? plate.positions : [];
    if (!fused) {
      const empty = document.createElement("div");
      empty.className = "plate-empty";
      empty.textContent = status;
      cells.appendChild(empty);
      return;
    }
    Array.from(fused).forEach((character, index) => {
      const position = positions.find((item) => Number(item.pos) === index + 1);
      addCharacterCell(cells, character, position && position.confidence, index + 1, "Fused character confidence");
    });
  }

  function imageUrl(filename) {
    return "/data/" + state.resultKind + "/" + encodeURIComponent(state.resultId) + "/vehicles/" + encodeURIComponent(filename);
  }

  function renderVehicleImage(trackId) {
    const image = byId("vehicle-image");
    const placeholder = byId("vehicle-placeholder");
    const prefix = "t" + trackId + "_vehicle_f";
    const filename = state.resultFiles.find((name) => name.startsWith(prefix) && name.endsWith(".jpg"));
    image.onerror = () => {
      image.hidden = true;
      placeholder.hidden = false;
    };
    if (!filename) {
      image.hidden = true;
      image.removeAttribute("src");
      placeholder.hidden = false;
      return;
    }
    image.alt = "Vehicle crop for track " + trackId;
    image.onload = () => { image.hidden = false; placeholder.hidden = true; };
    image.src = imageUrl(filename);
  }

  function renderFrameEvidence(vehicle) {
    const strip = byId("frame-evidence");
    strip.replaceChildren();
    const reads = Array.isArray(vehicle.plate && vehicle.plate.per_frame_reads) ? vehicle.plate.per_frame_reads : [];
    setText("frame-evidence-count", reads.length ? reads.length + (reads.length === 1 ? " frame read" : " frame reads") : "");
    byId("frame-evidence-empty").hidden = reads.length > 0;
    reads.forEach((read) => {
      const card = document.createElement("article");
      card.className = "frame-read-card";
      const frame = document.createElement("div");
      frame.className = "frame-read-image";
      const filename = "t" + vehicle.track_id + "_plate_f" + read.frame + ".jpg";
      if (state.resultFiles.includes(filename)) {
        const image = document.createElement("img");
        image.src = imageUrl(filename);
        image.alt = "Plate crop from frame " + read.frame;
        image.onerror = () => {
          image.remove();
          frame.textContent = "CROP UNAVAILABLE";
        };
        frame.appendChild(image);
      } else {
        frame.textContent = "FRAME " + read.frame;
      }
      const label = document.createElement("div");
      label.className = "frame-read-label";
      const readTime = window.TVExplain ? window.TVExplain.frameTime(read.frame, resultFps(state.result)) : null;
      label.textContent = "FRAME " + read.frame + (readTime ? " · " + readTime : "");
      const charRow = document.createElement("div");
      charRow.className = "read-character-row";
      const text = typeof read.text === "string" ? read.text : "";
      const probs = Array.isArray(read.char_probs)
        ? read.char_probs
        : typeof read.char_probs === "string"
          ? read.char_probs.trim().split(/[\s,]+/).filter(Boolean).map(Number)
          : [];
      if (text) {
        Array.from(text).forEach((character, index) => addCharacterCell(charRow, character, probs[index], index + 1, "OCR character confidence"));
      } else {
        charRow.textContent = "OCR text unavailable";
      }
      const quality = document.createElement("small");
      const height = read.height_px !== null && read.height_px !== undefined && read.height_px !== "" && Number.isFinite(Number(read.height_px)) ? " · crop " + read.height_px + " px high" : "";
      quality.className = "frame-read-quality";
      const qualityValue = read.quality === null || read.quality === undefined || read.quality === "" ? NaN : Number(read.quality);
      quality.textContent = "Frame quality score " + (Number.isFinite(qualityValue) ? qualityValue.toFixed(3) : "—") + height;
      card.append(frame, label, charRow, quality);
      card.addEventListener("click", () => seekToFrame(Number(read.frame)));
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.setAttribute("aria-label", "Seek to frame " + read.frame + " plate evidence");
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          seekToFrame(Number(read.frame));
        }
      });
      strip.appendChild(card);
    });
  }

  function renderCandidates(vehicle) {
    const list = byId("candidate-list");
    list.replaceChildren();
    const candidates = Array.isArray(vehicle.candidates) ? vehicle.candidates.slice().sort((a, b) => Number(a.rank) - Number(b.rank)).slice(0, 5) : [];
    byId("candidate-empty").hidden = candidates.length > 0;
    candidates.forEach((candidate, index) => {
      const card = document.createElement("article");
      card.className = "candidate-card";
      const head = document.createElement("div");
      head.className = "candidate-head";
      const rank = document.createElement("span");
      rank.className = "candidate-rank";
      rank.textContent = "#" + (candidate.rank || index + 1);
      const identity = document.createElement("div");
      identity.className = "candidate-identity";
      const registration = document.createElement("b");
      registration.className = "candidate-registration";
      registration.textContent = candidate.registration_number || candidate.synthetic_vehicle_id || "Candidate record";
      const synthetic = document.createElement("small");
      synthetic.textContent = candidate.synthetic_vehicle_id ? "Synthetic registry ID " + candidate.synthetic_vehicle_id : "Registry ID unavailable";
      identity.append(registration, synthetic);
      const score = document.createElement("b");
      score.className = "candidate-score";
      const scoreValue = candidate.match_score === null || candidate.match_score === undefined || candidate.match_score === "" ? NaN : Number(candidate.match_score);
      score.textContent = Number.isFinite(scoreValue) ? scoreValue.toFixed(1) : "—";
      const bar = document.createElement("div");
      bar.className = "candidate-bar";
      const fill = document.createElement("i");
      fill.style.width = (Number.isFinite(scoreValue) ? Math.max(0, Math.min(100, scoreValue)) : 0) + "%";
      bar.appendChild(fill);
      head.append(rank, identity, score);
      const X = window.TVExplain;
      // Component agreement scores exactly as stored by the matcher (0–1 each), and the lead over the next candidate.
      const parts = document.createElement("div");
      parts.className = "candidate-parts";
      [["Plate", candidate.plate_score], ["Colour", candidate.colour_score], ["Type", candidate.type_score]].forEach(([name, raw]) => {
        const value = raw === null || raw === undefined || raw === "" ? NaN : Number(raw);
        const chip = document.createElement("span");
        chip.className = "candidate-part" + (Number.isFinite(value) ? (value >= 0.999 ? " is-full" : value <= 0.001 ? " is-none" : " is-partial") : "");
        chip.textContent = name + " " + (Number.isFinite(value) ? value.toFixed(2) : "unknown");
        chip.title = name + " agreement used in the match score (1.00 = agrees, 0.00 = conflicts; unknown attributes are left out of the weighting).";
        parts.appendChild(chip);
      });
      const lead = X ? X.leadOverNext(candidates, index) : null;
      if (lead !== null) {
        const leadChip = document.createElement("span");
        leadChip.className = "candidate-lead";
        leadChip.textContent = "+" + lead.toFixed(1) + " over #" + (index + 2);
        parts.appendChild(leadChip);
      }
      const comparison = X ? X.compareCharacters(vehicle.plate && vehicle.plate.fused, candidate.registration_number) : null;
      const compareRow = document.createElement("div");
      compareRow.className = "plate-compare";
      if (comparison) {
        const counts = X.comparisonSummary(comparison);
        compareRow.setAttribute("aria-label", "Observed plate against " + candidate.registration_number + ": " + counts.exact + " same, " +
          counts.wildcard + " unread (?), " + counts.differs + " different");
        comparison.forEach((cell) => {
          const pair = document.createElement("span");
          pair.className = "compare-cell is-" + cell.state;
          pair.title = "Position " + cell.position + ": observed " + cell.observed + ", registry " + cell.registry +
            (cell.state === "wildcard" ? " (unread, kept as ?, treated as a wildcard)" : cell.state === "differs" ? " (differs; see the recorded reasons)" : "");
          const top = document.createElement("b");
          top.textContent = cell.observed;
          const bottom = document.createElement("small");
          bottom.textContent = cell.registry;
          pair.append(top, bottom);
          compareRow.appendChild(pair);
        });
        const legend = document.createElement("em");
        legend.textContent = counts.exact + " same · " + counts.wildcard + " unread (?) · " + counts.differs + " different";
        compareRow.appendChild(legend);
      } else {
        compareRow.classList.add("is-unavailable");
        compareRow.textContent = vehicle.plate && vehicle.plate.fused
          ? "Plates differ in length; the matcher compared them by edit distance (see the reasons)."
          : "No plate was read for this vehicle; the ranking rests on the recorded reasons below.";
      }
      const reasons = document.createElement("details");
      reasons.className = "candidate-reasons";
      reasons.open = index === 0;
      const summary = document.createElement("summary");
      summary.textContent = "Recorded reasons";
      const listReasons = document.createElement("ul");
      (Array.isArray(candidate.reasons) ? candidate.reasons : []).forEach((reason) => {
        const item = document.createElement("li");
        item.className = "reason-" + (X ? X.classifyReason(reason) : "supporting");
        item.textContent = String(reason);
        listReasons.appendChild(item);
      });
      if (!listReasons.children.length) {
        const item = document.createElement("li");
        item.textContent = "No ranking reasons were recorded.";
        listReasons.appendChild(item);
      }
      reasons.append(summary, listReasons);
      card.append(head, bar, parts, compareRow, reasons);
      list.appendChild(card);
    });
  }

  function selectVehicle(trackId) {
    const vehicle = (state.result && Array.isArray(state.result.vehicles) ? state.result.vehicles : [])
      .find((item) => String(item.track_id) === String(trackId));
    if (!vehicle) return;
    state.selectedTrackId = vehicle.track_id;
    document.querySelectorAll(".vehicle-row").forEach((row) => {
      const selected = row.dataset.trackId === String(vehicle.track_id);
      row.classList.toggle("is-selected", selected);
      row.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    byId("vehicle-detail").hidden = false;
    setText("detail-title", "Track " + vehicle.track_id);
    renderDecision(vehicle);
    renderVehicleImage(vehicle.track_id);
    setText("vehicle-type", vehicle.type && vehicle.type.label ? vehicle.type.label : "Not recorded");
    setText("type-source", vehicle.type && vehicle.type.source ? "Source: " + vehicle.type.source : "");
    const colour = vehicle.colour || {};
    setText("vehicle-colour", colour.label || "Unknown");
    setText("colour-confidence", colour.confidence !== null && colour.confidence !== undefined && colour.confidence !== "" && Number.isFinite(Number(colour.confidence)) ? "Attribute confidence " + percent(colour.confidence) : "Colour confidence not recorded");
    byId("colour-swatch").style.backgroundColor = swatchColor(colour.label);
    const firstFrame = vehicle.first_frame === null || vehicle.first_frame === undefined || vehicle.first_frame === "" ? NaN : Number(vehicle.first_frame);
    const lastFrame = vehicle.last_frame === null || vehicle.last_frame === undefined || vehicle.last_frame === "" ? NaN : Number(vehicle.last_frame);
    const fps = resultFps(state.result);
    const X = window.TVExplain;
    const firstTime = X ? X.frameTime(firstFrame, fps) : null;
    const lastTime = X ? X.frameTime(lastFrame, fps) : null;
    setText("track-frames", firstTime && lastTime ? firstTime + " – " + lastTime : "Not recorded");
    setText("track-duration", Number.isFinite(firstFrame) && Number.isFinite(lastFrame)
      ? "frames " + firstFrame + "–" + lastFrame + " · " + formatTime((lastFrame - firstFrame) / fps) + " span" : "");
    const merged = Array.isArray(vehicle.merged_track_ids) && vehicle.merged_track_ids.length > 1
      ? " · merged tracks " + vehicle.merged_track_ids.map((id) => "T" + id).join(", ") : "";
    setText("track-source", String(state.result.clip_id || state.resultId || "—"));
    setText("track-source-detail", (state.resultKind === "jobs" ? "uploaded clip" : "stored result") + " · track T" + vehicle.track_id + merged);
    renderDecisionLogic(vehicle);
    const detector = vehicle.type && vehicle.type.detector_conf_mean;
    const ocr = scoreConfidence(vehicle.plate && vehicle.plate.positions);
    const firstCandidate = Array.isArray(vehicle.candidates) ? vehicle.candidates.slice().sort((a, b) => Number(a.rank) - Number(b.rank))[0] : null;
    setScore("detector-score", "detector-meter", detector, 1);
    setScore("ocr-score", "ocr-meter", ocr, 1);
    setScore("match-score", "match-meter", firstCandidate && firstCandidate.match_score, 100);
    renderPlate(vehicle.plate || {});
    renderFrameEvidence(vehicle);
    renderCandidates(vehicle);
    drawTracks();
  }

  function buildTimelineMarkers(vehicles, frames) {
    const markers = byId("timeline-markers");
    markers.replaceChildren();
    const uniqueFrames = new Set();
    vehicles.forEach((vehicle) => {
      const reads = vehicle.plate && Array.isArray(vehicle.plate.per_frame_reads) ? vehicle.plate.per_frame_reads : [];
      reads.forEach((read) => {
        if (read.frame !== null && read.frame !== undefined && read.frame !== "" && Number.isFinite(Number(read.frame))) uniqueFrames.add(Number(read.frame));
      });
    });
    state.evidenceFrames = Array.from(uniqueFrames).sort((a, b) => a - b);
    const maxFrame = Math.max(1, frames - 1);
    state.evidenceFrames.forEach((frame) => {
      const mark = document.createElement("i");
      mark.className = "timeline-mark";
      mark.style.left = Math.max(0, Math.min(100, frame / maxFrame * 100)) + "%";
      mark.title = "Plate evidence at frame " + frame;
      markers.appendChild(mark);
    });
  }

  function timeFormatFromVideo() {
    const video = byId("result-video");
    const totalFrames = resultFrameCount(state.result);
    const fallback = totalFrames ? totalFrames / resultFps(state.result) : 0;
    const duration = Number.isFinite(video.duration) ? video.duration : fallback;
    return { current: Number(video.currentTime) || 0, duration: duration };
  }

  function updateVideoUI() {
    if (!state.result) return;
    const video = byId("result-video");
    const timing = timeFormatFromVideo();
    const duration = timing.duration;
    const ratio = duration > 0 ? Math.max(0, Math.min(1, timing.current / duration)) : 0;
    byId("timeline-progress").style.width = (ratio * 100) + "%";
    byId("seek-slider").value = String(Math.round(ratio * 1000));
    setText("viewer-time", formatTime(timing.current) + " / " + (duration ? formatTime(duration) : "—"));
    const frame = Math.round(timing.current * resultFps(state.result));
    const last = Math.max(0, resultFrameCount(state.result) - 1);
    setText("viewer-frame", "FRAME " + frame + " / " + (resultFrameCount(state.result) ? last : "—"));
    const play = byId("play-toggle");
    play.textContent = video.paused ? "▶" : "Ⅱ";
    play.setAttribute("aria-label", video.paused ? "Play video" : "Pause video");
    drawTracks();
  }

  function seekToFrame(frame) {
    const video = byId("result-video");
    if (!Number.isFinite(frame) || !state.result) return;
    video.currentTime = Math.max(0, frame / resultFps(state.result));
    updateVideoUI();
  }

  function sizeVideoOverlay() {
    if (!state.result) return;
    const video = byId("result-video");
    const canvas = byId("track-canvas");
    if (!video.videoWidth || !video.videoHeight) return;
    const stage = byId("video-stage");
    const scale = Math.min(stage.clientWidth / video.videoWidth, stage.clientHeight / video.videoHeight);
    if (!Number.isFinite(scale) || scale <= 0) return;
    const width = Math.round(video.videoWidth * scale);
    const height = Math.round(video.videoHeight * scale);
    video.style.width = width + "px";
    video.style.height = height + "px";
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
    drawTracks();
  }

  function boxAtFrame(vehicle, frame) {
    const track = Array.isArray(vehicle.track) ? vehicle.track : [];
    let nearest = null;
    let distance = Infinity;
    track.forEach((point) => {
      if (!Array.isArray(point) || point.length < 5) return;
      const delta = Math.abs(Number(point[0]) - frame);
      if (delta < distance) {
        nearest = point;
        distance = delta;
      }
    });
    return distance <= 1 && nearest ? nearest.slice(1, 5).map(Number) : null;
  }

  function drawTracks() {
    const canvas = byId("track-canvas");
    const context = canvas && canvas.getContext ? canvas.getContext("2d") : null;
    if (!context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    const video = byId("result-video");
    if (!state.result || !video.videoWidth || !canvas.width) return;
    const frame = Math.round((Number(video.currentTime) || 0) * resultFps(state.result));
    const vehicles = Array.isArray(state.result.vehicles) ? state.result.vehicles : [];
    vehicles.forEach((vehicle) => {
      const box = boxAtFrame(vehicle, frame);
      if (!box) return;
      const selected = String(vehicle.track_id) === String(state.selectedTrackId);
      context.lineWidth = selected ? 3 : 1.6;
      context.strokeStyle = selected ? "#7aa7ff" : "#6ee4f1";
      context.fillStyle = selected ? "rgba(122,167,255,.08)" : "rgba(110,228,241,.035)";
      const width = box[2] - box[0];
      const height = box[3] - box[1];
      context.fillRect(box[0], box[1], width, height);
      context.strokeRect(box[0], box[1], width, height);
      context.font = "bold 17px Consolas, monospace";
      context.textBaseline = "bottom";
      const label = "T" + vehicle.track_id;
      const labelWidth = context.measureText(label).width + 12;
      context.fillStyle = selected ? "#7aa7ff" : "#6ee4f1";
      context.fillRect(box[0], Math.max(0, box[1] - 23), labelWidth, 22);
      context.fillStyle = "#080a11";
      context.fillText(label, box[0] + 6, Math.max(17, box[1] - 5));
    });
  }

  function selectTrackAtPoint(event) {
    if (!state.result) return;
    const canvas = byId("track-canvas");
    const rect = canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width * canvas.width;
    const y = (event.clientY - rect.top) / rect.height * canvas.height;
    const frame = Math.round((Number(byId("result-video").currentTime) || 0) * resultFps(state.result));
    const vehicles = Array.isArray(state.result.vehicles) ? state.result.vehicles.slice().reverse() : [];
    const match = vehicles.find((vehicle) => {
      const box = boxAtFrame(vehicle, frame);
      return box && x >= box[0] && x <= box[2] && y >= box[1] && y <= box[3];
    });
    if (match) selectVehicle(match.track_id);
  }

  async function ensureOverview() {
    if (!state.overview) await refreshOverview(false);
    return state.overview;
  }

  async function loadReviewData() {
    if (state.review) return state.review;
    if (state.reviewPromise) return state.reviewPromise;
    state.reviewPromise = fetch("/api/review", { cache: "no-store" }).then((response) => {
      if (!response.ok) throw new Error("Review data returned HTTP " + response.status + ".");
      return response.json();
    }).then((data) => {
      state.review = data;
      return data;
    }).catch((error) => {
      state.reviewPromise = null;
      throw error;
    });
    return state.reviewPromise;
  }

  function showReviewError(view, error) {
    if (view === "crosscam") {
      byId("crosscam-loading").hidden = true;
      const target = byId("crosscam-error");
      target.textContent = error && error.message ? error.message : "Cross-camera files could not be loaded.";
      target.hidden = false;
    } else if (view === "insights") {
      const target = byId("insights-error");
      target.textContent = error && error.message ? error.message : "Evaluation files could not be loaded.";
      target.hidden = false;
    }
  }

  async function loadReviewView(view) {
    const requestId = ++state.reviewRequestId;
    if (view === "reports") {
      try {
        await ensureOverview();
        if (requestId !== state.reviewRequestId || window.location.hash !== "#reports") return;
        renderReportView();
      } catch (error) {
        showReviewError(view, error);
      }
      return;
    }
    if (view === "crosscam") {
      byId("crosscam-loading").hidden = false;
      byId("crosscam-content").hidden = true;
      byId("crosscam-error").hidden = true;
    } else {
      byId("insights-error").hidden = true;
    }
    try {
      const tasks = [loadReviewData()];
      if (!state.overview) tasks.push(ensureOverview());
      await Promise.all(tasks);
      if (requestId !== state.reviewRequestId || window.location.hash !== "#" + view) return;
      if (view === "crosscam") renderCrosscamView();
      else renderInsightsView();
    } catch (error) {
      if (requestId === state.reviewRequestId) showReviewError(view, error);
    }
  }

  function renderReportView() {
    const clips = state.overview && Array.isArray(state.overview.clips)
      ? state.overview.clips.filter((clip) => clip.has_report)
      : [];
    const select = byId("report-clip-select");
    select.replaceChildren();
    byId("report-empty").hidden = clips.length > 0;
    byId("report-preview-wrap").hidden = clips.length === 0;
    const htmlLink = byId("download-report-html");
    const pdfLink = byId("download-report-pdf");
    const openLink = byId("open-report-tab");
    if (!clips.length) {
      htmlLink.hidden = true;
      pdfLink.hidden = true;
      return;
    }
    clips.forEach((clip) => {
      const option = document.createElement("option");
      option.value = clip.clip_id;
      option.textContent = clip.clip_id + " · " + (clip.camera_type || "camera type unknown");
      select.appendChild(option);
    });
    const selected = clips.find((clip) => clip.clip_id === state.selectedReportClip) || clips[0];
    state.selectedReportClip = selected.clip_id;
    select.value = selected.clip_id;
    const htmlUrl = "/runs/" + encodeURIComponent(selected.clip_id) + "/report";
    const pdfUrl = "/runs/" + encodeURIComponent(selected.clip_id) + "/report.pdf";
    htmlLink.href = htmlUrl;
    htmlLink.download = selected.clip_id + "-report.html";
    htmlLink.hidden = false;
    openLink.href = htmlUrl;
    byId("report-preview").src = htmlUrl;
    setText("report-preview-label", selected.clip_id + " · HTML REPORT PREVIEW");
    pdfLink.href = pdfUrl;
    pdfLink.download = selected.clip_id + "-report.pdf";
    pdfLink.hidden = !selected.has_report_pdf;
  }

  function fractionFromReport(value) {
    const match = String(value == null ? "" : value).match(/(\d+)\s*\/\s*(\d+)/);
    if (!match) return null;
    const numerator = Number(match[1]);
    const denominator = Number(match[2]);
    return { numerator: numerator, denominator: denominator, percent: denominator > 0 ? Math.max(0, Math.min(100, numerator / denominator * 100)) : 0 };
  }

  function appendMetricBar(container, label, value, tone, key) {
    const metric = document.createElement("article");
    metric.className = "insight-metric panel";
    metric.title = metricExplanation(key, label);
    metric.tabIndex = 0;
    metric.setAttribute("aria-label", label + ": " + String(value == null ? "not reported" : value) + ". " + metric.title);
    const top = document.createElement("div");
    top.className = "insight-metric-top";
    const title = document.createElement("span");
    title.textContent = label;
    const amount = document.createElement("b");
    amount.textContent = value == null || value === "" ? "Not reported" : String(value);
    top.append(title, amount);
    const rail = document.createElement("div");
    rail.className = "insight-metric-rail " + (tone || "");
    const fill = document.createElement("i");
    const ratio = fractionFromReport(value);
    fill.style.width = ratio ? ratio.percent + "%" : "0%";
    rail.appendChild(fill);
    metric.append(top, rail);
    container.appendChild(metric);
  }

  function displayVariantName(value) {
    return String(value || "").replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function renderInsightsView() {
    const evaluation = state.overview && state.overview.evaluation ? state.overview.evaluation : {};
    const metrics = Array.isArray(evaluation.metrics) ? evaluation.metrics : [];
    const grid = byId("insight-metric-grid");
    grid.replaceChildren();
    const metricTones = {
      registered_matches: "good",
      false_confident_matches: "error",
      wrong_plate_characters: "error",
      detected_and_tracked: "cyan",
      plate_characters_correct: "good",
      type_compatible: "cyan",
    };
    metrics.forEach((metric) => appendMetricBar(grid, metric.label, metric.value, metricTones[metric.key], metric.key));
    if (!metrics.length) {
      const empty = document.createElement("div");
      empty.className = "insight-empty panel";
      empty.textContent = "Evaluation headline metrics are not present in the local report.";
      grid.appendChild(empty);
    }
    setText("insight-clip-count", evaluation.clip_count ? evaluation.clip_count + " clips in the evaluation" : "Clip count not reported");
    const sourceNames = [evaluation.source || "p6_evaluation.md", "p6_robustness.json", "crosscam_evaluation.json"];
    setText("insights-source", "LIVE FILES · " + sourceNames.join(" · "));
    renderRobustnessChart(state.review && state.review.robustness);
    renderCrosscamOutcomeChart(state.review && state.review.crosscam_evaluation);
  }

  function appendRobustMetric(row, label, value, tone) {
    const cell = document.createElement("div");
    cell.className = "robust-metric " + (tone || "");
    cell.title = label + " across the degraded-video variant, as reported in p6_robustness.json. Value: " + String(value == null ? "not reported" : value) + ".";
    cell.tabIndex = 0;
    cell.setAttribute("aria-label", cell.title);
    const title = document.createElement("span");
    title.textContent = label;
    const valueNode = document.createElement("b");
    valueNode.textContent = value == null || value === "" ? "Not reported" : String(value);
    const rail = document.createElement("div");
    rail.className = "robust-metric-rail";
    const fill = document.createElement("i");
    const ratio = fractionFromReport(value);
    fill.style.width = ratio ? ratio.percent + "%" : "0%";
    rail.appendChild(fill);
    cell.append(title, valueNode, rail);
    row.appendChild(cell);
  }

  function renderRobustnessChart(data) {
    const chart = byId("robustness-chart");
    chart.replaceChildren();
    const variants = data && data.variants && typeof data.variants === "object" ? data.variants : {};
    const entries = Object.entries(variants);
    entries.forEach(([name, values]) => {
      const row = document.createElement("article");
      row.className = "robustness-row";
      const heading = document.createElement("h3");
      heading.textContent = displayVariantName(name);
      const metrics = document.createElement("div");
      metrics.className = "robustness-row-metrics";
      appendRobustMetric(metrics, "Registered match", values.registered_vehicles_matched_correctly, "good");
      appendRobustMetric(metrics, "False confident", values.unregistered_with_false_confident_match, "error");
      appendRobustMetric(metrics, "Wrong characters", values.plate_chars_WRONG, "error");
      row.append(heading, metrics);
      chart.appendChild(row);
    });
    if (!entries.length) {
      const empty = document.createElement("div");
      empty.className = "insight-empty";
      empty.textContent = "No degradation variants were found in p6_robustness.json.";
      chart.appendChild(empty);
    }
  }

  function renderCrosscamOutcomeChart(data) {
    const chart = byId("crosscam-outcome-chart");
    chart.replaceChildren();
    const groups = data && Array.isArray(data.groups) ? data.groups : [];
    const summary = data && data.summary ? data.summary : {};
    const counts = [
      ["Correct link", groups.filter((group) => /correct link/i.test(String(group.outcome))).length, "good"],
      ["Missed link", groups.filter((group) => /no link.*missed/i.test(String(group.outcome))).length, "warn"],
      ["Wrong link", Number(summary.wrong_links_on_groups) || 0, "error"],
      ["Not tracked", groups.filter((group) => /not tracked/i.test(String(group.outcome))).length, "error"],
    ];
    const total = groups.length || Number(summary.groups) || 0;
    setText("crosscam-insight-total", total + (total === 1 ? " labelled group" : " labelled groups"));
    const max = Math.max(1, ...counts.map((entry) => entry[1]));
    counts.forEach(([label, count, tone]) => {
      const row = document.createElement("div");
      row.className = "crosscam-outcome-row " + tone;
      const name = document.createElement("span");
      name.textContent = label;
      const rail = document.createElement("div");
      rail.className = "crosscam-outcome-rail";
      const fill = document.createElement("i");
      fill.style.width = (count / max * 100) + "%";
      rail.appendChild(fill);
      const value = document.createElement("b");
      value.textContent = String(count);
      row.append(name, rail, value);
      chart.appendChild(row);
    });
    setText("crosscam-eval-note", data && data.note ? data.note : "Evaluation note unavailable.");
  }

  function renderCrosscamView() {
    const pairs = state.review && Array.isArray(state.review.crosscam_pairs) ? state.review.crosscam_pairs : [];
    const select = byId("crosscam-pair-select");
    select.replaceChildren();
    setText("crosscam-source", pairs.length ? "LIVE FILES · runs/crosscam/*.json" : "NO PAIR FILES FOUND");
    byId("crosscam-loading").hidden = true;
    byId("crosscam-content").hidden = false;
    pairs.forEach((pair) => {
      const option = document.createElement("option");
      option.value = pair.clip_a + "__" + pair.clip_b;
      option.textContent = pair.clip_a + " ↔ " + pair.clip_b;
      select.appendChild(option);
    });
    setText("crosscam-pair-count", String(pairs.length));
    if (!pairs.length) {
      byId("pair-video-grid").hidden = true;
      byId("pair-label-list").replaceChildren();
      byId("pair-label-empty").hidden = false;
      byId("pair-decision-list").replaceChildren();
      byId("pair-decision-empty").hidden = false;
      return;
    }
    byId("pair-video-grid").hidden = false;
    const selected = pairs.find((pair) => pair.clip_a + "__" + pair.clip_b === state.selectedCrosscamPair) || pairs[0];
    state.selectedCrosscamPair = selected.clip_a + "__" + selected.clip_b;
    select.value = state.selectedCrosscamPair;
    loadCrosscamPair(selected);
  }

  function fetchStoredRun(clipId) {
    return fetch("/data/runs/" + encodeURIComponent(clipId) + "/result.json", { cache: "no-store" }).then((response) => {
      if (!response.ok) throw new Error("Stored result for " + clipId + " returned HTTP " + response.status + ".");
      return response.json();
    }).catch(() => null);
  }

  async function loadCrosscamPair(pair) {
    const requestId = ++state.crosscamPairRequestId;
    state.selectedCrosscamPair = pair.clip_a + "__" + pair.clip_b;
    setText("pair-clip-a-title", pair.clip_a);
    setText("pair-clip-b-title", pair.clip_b);
    setText("crosscam-pair-caption", (Array.isArray(pair.directions) ? pair.directions.length : 0) + " recorded direction(s); decisions remain separate");
    state.selectedCrosscamTracks = {};
    const [resultA, resultB] = await Promise.all([fetchStoredRun(pair.clip_a), fetchStoredRun(pair.clip_b)]);
    if (requestId !== state.crosscamPairRequestId || window.location.hash !== "#crosscam") return;
    state.crosscamResults = {};
    if (resultA) state.crosscamResults[pair.clip_a] = resultA;
    if (resultB) state.crosscamResults[pair.clip_b] = resultB;
    renderCrosscamVideos(pair, resultA, resultB);
    renderPairEvaluation(pair);
    renderPairDecisions(pair);
    renderPairJoint(pair);
  }

  // Joint same-scene links (crosscam.py link_pair, DECISIONS M16): the output that crosscam_evaluation.json scores.
  // "confirmed (plate)" links rest on agreeing plate characters; "probable (...)" links come from appearance/type/colour
  // by elimination inside an owner-declared pair and are shown as such, never as an identity.
  function renderPairJoint(pair) {
    const list = byId("pair-joint-list");
    const note = byId("pair-joint-note");
    if (!list) return;
    list.replaceChildren();
    const joint = pair && pair.same_scene && Array.isArray(pair.same_scene.links) ? pair.same_scene : null;
    const links = joint ? joint.links : [];
    byId("pair-joint-empty").hidden = links.length > 0;
    links.forEach((link, index) => {
      const a = link.a || {};
      const b = link.b || {};
      const confirmed = /^confirmed/i.test(String(link.link || ""));
      const row = document.createElement("article");
      row.className = "pair-decision-row " + (confirmed ? "is-linked" : "is-probable");
      const leftNode = document.createElement("div");
      leftNode.className = "pair-node-slot";
      appendPairNode(leftNode, a.clip_id || pair.clip_a, a.track_id, { plate: a.plate });
      const connector = document.createElement("div");
      connector.className = "pair-link-connector " + (confirmed ? "is-linked" : "is-probable");
      const line = document.createElement("i");
      line.className = "pair-link-line";
      const stateLabel = document.createElement("b");
      stateLabel.textContent = confirmed ? "CONFIRMED · PLATE" : "PROBABLE · NOT AN IDENTITY";
      const scoreNode = document.createElement("small");
      const score = Number(link.link_score);
      scoreNode.textContent = Number.isFinite(score) ? "link score " + score.toFixed(1) + " / 100" : "No score";
      connector.append(line, stateLabel, scoreNode);
      const rightNode = document.createElement("div");
      rightNode.className = "pair-node-slot";
      appendPairNode(rightNode, b.clip_id || pair.clip_b, b.track_id, { plate: b.plate });
      const detail = document.createElement("details");
      detail.className = "pair-decision-details";
      detail.open = index === 0;
      const summary = document.createElement("summary");
      summary.textContent = "Joint link · " + String(link.link || "kind not recorded");
      const body = document.createElement("div");
      body.className = "pair-detail-body";
      appendReasons(body, link.evidence, "No evidence text was recorded for this link.");
      const final = link.final;
      if (final && typeof final === "object") {
        const pooled = document.createElement("div");
        pooled.className = "joint-final";
        const heading = document.createElement("span");
        heading.className = "viewer-kicker";
        heading.textContent = "POOLED ACROSS BOTH CAMERAS";
        const facts = document.createElement("p");
        const plate = final.plate ? final.plate : "no plate";
        facts.textContent = "Plate " + plate + " · " + (final.type || "type unknown") + " · " + (final.colour || "colour unknown") +
          (Number.isFinite(Number(final.reads_pooled)) ? " · " + final.reads_pooled + " plate reads pooled" : "");
        const decision = document.createElement("p");
        decision.className = "joint-final-decision is-" + decisionClass(final.decision);
        decision.textContent = "Registry: " + decisionLabel(final.decision) +
          (final.registry_top1 ? " · top record " + final.registry_top1 : "") +
          (Number.isFinite(Number(final.match_score)) ? " · match score " + Number(final.match_score).toFixed(1) + " (not a probability)" : "") +
          (final.reason ? " · " + final.reason : "");
        pooled.append(heading, facts, decision);
        body.appendChild(pooled);
      }
      detail.append(summary, body);
      row.append(leftNode, connector, rightNode, detail);
      list.appendChild(row);
    });
    if (links.length) {
      const first = links[0];
      if (first.a && first.b) {
        state.selectedCrosscamTracks[first.a.clip_id || pair.clip_a] = first.a.track_id;
        state.selectedCrosscamTracks[first.b.clip_id || pair.clip_b] = first.b.track_id;
        drawPairTracks(pair.clip_a, "a");
        drawPairTracks(pair.clip_b, "b");
      }
    }
    if (note) {
      const parts = [];
      if (joint && Array.isArray(joint.unlinked_a) && joint.unlinked_a.length) parts.push(pair.clip_a + " unlinked: " + joint.unlinked_a.map((t) => "T" + t).join(", "));
      if (joint && Array.isArray(joint.unlinked_b) && joint.unlinked_b.length) parts.push(pair.clip_b + " unlinked: " + joint.unlinked_b.map((t) => "T" + t).join(", "));
      const folded = joint && joint.duplicates_folded ? Object.entries(joint.duplicates_folded).flatMap(([side, map]) =>
        Object.entries(map || {}).map(([from, to]) => (side === "a" ? pair.clip_a : pair.clip_b) + " T" + from + " folded into T" + to)) : [];
      if (folded.length) parts.push("Nested duplicate tracks: " + folded.join("; "));
      note.textContent = joint ? (joint.note ? joint.note + " " : "") + parts.join(" · ") : "";
    }
  }

  function renderCrosscamVideos(pair, resultA, resultB) {
    const setup = (clipId, side, result) => {
      const video = byId("pair-video-" + side);
      const canvas = byId("pair-canvas-" + side);
      const missing = byId("pair-video-" + side + "-missing");
      setText("pair-clip-" + side + "-title", clipId);
      const vehicles = result && Array.isArray(result.vehicles) ? result.vehicles : [];
      setText("pair-clip-" + side + "-count", result ? vehicles.length + " tracks" : "Result unavailable");
      video.pause();
      video.onerror = () => { missing.hidden = false; canvas.hidden = true; };
      video.onloadedmetadata = () => { missing.hidden = true; canvas.hidden = false; sizePairVideo(clipId, side); };
      video.removeAttribute("src");
      video.load();
      missing.hidden = true;
      canvas.hidden = false;
      video.src = "/data/runs/" + encodeURIComponent(clipId) + "/video";
      video.load();
      video.ontimeupdate = () => drawPairTracks(clipId, side);
      if (!result) {
        missing.hidden = false;
        canvas.hidden = true;
      }
    };
    setup(pair.clip_a, "a", resultA);
    setup(pair.clip_b, "b", resultB);
  }

  function sizePairVideo(clipId, side) {
    const result = state.crosscamResults[clipId];
    const video = byId("pair-video-" + side);
    const canvas = byId("pair-canvas-" + side);
    const stage = video.parentElement;
    if (!result || !video.videoWidth || !video.videoHeight) return;
    const scale = Math.min(stage.clientWidth / video.videoWidth, stage.clientHeight / video.videoHeight);
    if (!Number.isFinite(scale) || scale <= 0) return;
    const width = Math.round(video.videoWidth * scale);
    const height = Math.round(video.videoHeight * scale);
    video.style.width = width + "px";
    video.style.height = height + "px";
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
    drawPairTracks(clipId, side);
  }

  function drawPairTracks(clipId, side) {
    const canvas = byId("pair-canvas-" + side);
    const context = canvas && canvas.getContext ? canvas.getContext("2d") : null;
    if (!context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    const result = state.crosscamResults[clipId];
    const video = byId("pair-video-" + side);
    if (!result || !video.videoWidth || !canvas.width) return;
    const frame = Math.round((Number(video.currentTime) || 0) * resultFps(result));
    const vehicles = Array.isArray(result.vehicles) ? result.vehicles : [];
    vehicles.forEach((vehicle) => {
      const box = boxAtFrame(vehicle, frame);
      if (!box) return;
      const selected = String(vehicle.track_id) === String(state.selectedCrosscamTracks[clipId]);
      context.lineWidth = selected ? 3 : 1.5;
      context.strokeStyle = selected ? "#7aa7ff" : "#6ee4f1";
      context.fillStyle = selected ? "rgba(122,167,255,.09)" : "rgba(110,228,241,.035)";
      context.fillRect(box[0], box[1], box[2] - box[0], box[3] - box[1]);
      context.strokeRect(box[0], box[1], box[2] - box[0], box[3] - box[1]);
      const label = "T" + vehicle.track_id;
      context.font = "bold 16px Consolas, monospace";
      const labelWidth = context.measureText(label).width + 10;
      context.fillStyle = selected ? "#7aa7ff" : "#6ee4f1";
      context.fillRect(box[0], Math.max(0, box[1] - 21), labelWidth, 20);
      context.fillStyle = "#080a11";
      context.textBaseline = "bottom";
      context.fillText(label, box[0] + 5, Math.max(16, box[1] - 4));
    });
  }

  function focusPairTrack(clipId, trackId) {
    if (trackId === null || trackId === undefined) return;
    state.selectedCrosscamTracks[clipId] = trackId;
    const result = state.crosscamResults[clipId];
    const vehicle = result && Array.isArray(result.vehicles)
      ? result.vehicles.find((item) => String(item.track_id) === String(trackId))
      : null;
    const side = clipId === state.selectedCrosscamPair.split("__")[0] ? "a" : "b";
    const video = byId("pair-video-" + side);
    if (vehicle && Number.isFinite(Number(vehicle.first_frame)) && Number.isFinite(resultFps(result))) {
      video.currentTime = Number(vehicle.first_frame) / resultFps(result);
    }
    drawPairTracks(clipId, side);
  }

  function vehicleForCrosscam(clipId, trackId) {
    const result = state.crosscamResults[clipId];
    return result && Array.isArray(result.vehicles)
      ? result.vehicles.find((vehicle) => String(vehicle.track_id) === String(trackId))
      : null;
  }

  function appendPairNode(container, clipId, trackId, fallback) {
    const vehicle = vehicleForCrosscam(clipId, trackId);
    const node = document.createElement("button");
    node.type = "button";
    node.className = "pair-vehicle-node";
    node.disabled = trackId === null || trackId === undefined;
    const identifier = document.createElement("span");
    identifier.className = "pair-node-id";
    identifier.textContent = trackId === null || trackId === undefined ? "NO TRACK" : clipId + " · T" + trackId;
    const plate = vehicle && vehicle.plate && vehicle.plate.fused
      ? vehicle.plate.fused
      : fallback && fallback.plate ? fallback.plate : "Plate unavailable";
    const registration = document.createElement("b");
    registration.className = "pair-node-plate";
    registration.textContent = plate;
    const attributes = document.createElement("small");
    const type = vehicle && vehicle.type && vehicle.type.label ? vehicle.type.label : fallback && fallback.type ? fallback.type : "Type unavailable";
    const colour = vehicle && vehicle.colour && vehicle.colour.label ? vehicle.colour.label : fallback && fallback.colour ? fallback.colour : "Colour unavailable";
    attributes.textContent = type + " · " + colour;
    node.append(identifier, registration, attributes);
    node.addEventListener("click", () => focusPairTrack(clipId, trackId));
    container.appendChild(node);
  }

  function appendScoreParts(container, parts) {
    if (!parts || typeof parts !== "object") return;
    const grid = document.createElement("div");
    grid.className = "link-score-parts";
    Object.entries(parts).forEach(([name, value]) => {
      const cell = document.createElement("span");
      cell.className = "link-score-part";
      const numeric = value === null || value === undefined || value === "" ? NaN : Number(value);
      cell.textContent = displayVariantName(name) + " " + (Number.isFinite(numeric) ? percent(numeric) : String(value));
      grid.appendChild(cell);
    });
    container.appendChild(grid);
  }

  function appendReasons(container, reasons, fallback) {
    const list = document.createElement("ul");
    list.className = "link-reasons";
    const items = Array.isArray(reasons) && reasons.length ? reasons : fallback ? [fallback] : [];
    items.forEach((reason) => {
      const item = document.createElement("li");
      item.textContent = String(reason);
      list.appendChild(item);
    });
    if (!items.length) {
      const item = document.createElement("li");
      item.textContent = "No reasoning text was recorded for this direction.";
      list.appendChild(item);
    }
    container.appendChild(list);
  }

  function renderCandidateEvidence(container, candidates, targetClip) {
    if (!Array.isArray(candidates) || !candidates.length) return;
    const wrapper = document.createElement("div");
    wrapper.className = "pair-candidate-evidence";
    candidates.forEach((candidate) => {
      const item = document.createElement("article");
      item.className = "pair-candidate-item";
      const head = document.createElement("div");
      head.className = "pair-candidate-head";
      const identity = document.createElement("b");
      identity.textContent = (candidate.clip_id || targetClip) + " · T" + candidate.track_id;
      const score = document.createElement("strong");
      const numeric = candidate.link_score === null || candidate.link_score === undefined ? NaN : Number(candidate.link_score);
      score.textContent = Number.isFinite(numeric) ? numeric.toFixed(1) : "—";
      head.append(identity, score);
      const evidence = document.createElement("small");
      evidence.textContent = candidate.evidence || "Evidence type not recorded";
      item.append(head, evidence);
      appendScoreParts(item, candidate.parts);
      appendReasons(item, candidate.reasons, "");
      wrapper.appendChild(item);
    });
    container.appendChild(wrapper);
  }

  function renderPairDecisions(pair) {
    const list = byId("pair-decision-list");
    list.replaceChildren();
    const decisions = [];
    (Array.isArray(pair.directions) ? pair.directions : []).forEach((direction) => {
      (Array.isArray(direction.links) ? direction.links : []).forEach((link) => decisions.push({ direction: direction, link: link }));
    });
    byId("pair-decision-empty").hidden = decisions.length > 0;
    setText("crosscam-pair-count", String(decisions.length));
    state.selectedCrosscamTracks = {};
    decisions.forEach((item, index) => {
      const direction = item.direction;
      const link = item.link;
      const sourceClip = link.clip_id || direction.source_clip;
      const targetClip = direction.target_clip;
      const candidates = Array.isArray(link.candidates) ? link.candidates : [];
      const isLinked = link.decision === "link" && link.linked_to;
      const scoredTarget = isLinked ? link.linked_to : candidates[0] || null;
      const sourceTrack = link.track_id;
      const targetTrack = scoredTarget ? scoredTarget.track_id : null;
      const leftClip = pair.clip_a;
      const rightClip = pair.clip_b;
      const leftTrack = sourceClip === leftClip ? sourceTrack : targetTrack;
      const rightTrack = sourceClip === rightClip ? sourceTrack : targetTrack;
      const leftFallback = sourceClip === leftClip ? link : null;
      const rightFallback = sourceClip === rightClip ? link : null;
      const row = document.createElement("article");
      row.className = "pair-decision-row " + (isLinked ? "is-linked" : "is-unlinked");
      const leftNode = document.createElement("div");
      leftNode.className = "pair-node-slot";
      appendPairNode(leftNode, leftClip, leftTrack, leftFallback);
      const connector = document.createElement("div");
      // Nodes keep a fixed layout (camera A left, camera B right); the arrow follows the recorded direction.
      connector.className = "pair-link-connector " + (isLinked ? "is-linked" : "is-unlinked") + (sourceClip === rightClip ? " is-reverse" : "");
      connector.title = "Recorded direction: " + sourceClip + " → " + targetClip;
      const line = document.createElement("i");
      line.className = "pair-link-line";
      const stateLabel = document.createElement("b");
      stateLabel.textContent = isLinked ? "LINK" : "NO LINK";
      const scoreNode = document.createElement("small");
      const scoreValue = scoredTarget && Number.isFinite(Number(scoredTarget.link_score)) ? Number(scoredTarget.link_score) : NaN;
      scoreNode.textContent = Number.isFinite(scoreValue) ? scoreValue.toFixed(1) + " / 100" : "No score";
      connector.append(line, stateLabel, scoreNode);
      const rightNode = document.createElement("div");
      rightNode.className = "pair-node-slot";
      appendPairNode(rightNode, rightClip, rightTrack, rightFallback);
      const detail = document.createElement("details");
      detail.className = "pair-decision-details";
      const summary = document.createElement("summary");
      summary.textContent = direction.source_clip + " → " + direction.target_clip + " · T" + sourceTrack + " · " + (link.decision || "decision unavailable");
      const body = document.createElement("div");
      body.className = "pair-detail-body";
      const reason = document.createElement("p");
      reason.textContent = link.decision_reason || "Decision reason not recorded.";
      body.appendChild(reason);
      if (scoredTarget) {
        const evidence = document.createElement("p");
        evidence.className = "pair-evidence-label";
        evidence.textContent = "Evidence: " + (scoredTarget.evidence || "not recorded");
        body.appendChild(evidence);
        appendScoreParts(body, scoredTarget.parts);
        appendReasons(body, scoredTarget.reasons, link.decision_reason);
      }
      if (!isLinked && candidates.length) {
        const pool = document.createElement("details");
        pool.className = "pair-pool-details";
        const poolSummary = document.createElement("summary");
        poolSummary.textContent = "All " + candidates.length + " recorded candidate(s)";
        pool.appendChild(poolSummary);
        renderCandidateEvidence(pool, candidates, targetClip);
        body.appendChild(pool);
      }
      detail.append(summary, body);
      row.append(leftNode, connector, rightNode, detail);
      list.appendChild(row);
      if (index === 0 && sourceTrack !== null && targetTrack !== null) {
        state.selectedCrosscamTracks[sourceClip] = sourceTrack;
        state.selectedCrosscamTracks[targetClip] = targetTrack;
      }
    });
    drawPairTracks(pair.clip_a, "a");
    drawPairTracks(pair.clip_b, "b");
  }

  function renderPairEvaluation(pair) {
    const data = state.review && state.review.crosscam_evaluation;
    const groups = data && Array.isArray(data.groups) ? data.groups.filter((group) =>
      (group.clip_a === pair.clip_a && group.clip_b === pair.clip_b) || (group.clip_a === pair.clip_b && group.clip_b === pair.clip_a)
    ) : [];
    const list = byId("pair-label-list");
    list.replaceChildren();
    byId("pair-label-empty").hidden = groups.length > 0;
    groups.forEach((group) => {
      const card = document.createElement("article");
      const outcome = String(group.outcome || "not reported");
      const outcomeClass = /correct link/i.test(outcome) ? "good" : /not tracked/i.test(outcome) ? "error" : /wrong/i.test(outcome) ? "error" : "warn";
      card.className = "pair-label-card " + outcomeClass;
      const heading = document.createElement("div");
      heading.className = "pair-label-heading";
      const groupName = document.createElement("b");
      groupName.textContent = group.group || "Evaluation group";
      const status = document.createElement("span");
      status.textContent = outcome.toUpperCase();
      heading.append(groupName, status);
      const bodies = document.createElement("div");
      bodies.className = "pair-label-bodies";
      [[group.clip_a, group.a, group.plate_a], [group.clip_b, group.b, group.plate_b]].forEach((entry) => {
        const body = document.createElement("div");
        const label = document.createElement("span");
        label.textContent = String(entry[0] || "Clip") + " · label " + String(entry[1] || "not recorded");
        const plate = document.createElement("b");
        plate.textContent = entry[2] ? String(entry[2]) : "Reference plate not recorded";
        body.append(label, plate);
        bodies.appendChild(body);
      });
      card.append(heading, bodies);
      list.appendChild(card);
    });
  }

  function bindReviewControls() {
    byId("crosscam-pair-select").addEventListener("change", (event) => {
      const pairs = state.review && Array.isArray(state.review.crosscam_pairs) ? state.review.crosscam_pairs : [];
      const pair = pairs.find((item) => item.clip_a + "__" + item.clip_b === event.target.value);
      if (pair) loadCrosscamPair(pair);
    });
    byId("play-pair-toggle").addEventListener("click", () => {
      const left = byId("pair-video-a");
      const right = byId("pair-video-b");
      if (left.paused || right.paused) {
        left.play().catch(() => showToast("Camera A playback could not start."));
        right.play().catch(() => showToast("Camera B playback could not start."));
      } else {
        left.pause();
        right.pause();
      }
    });
    byId("report-clip-select").addEventListener("change", (event) => {
      state.selectedReportClip = event.target.value;
      renderReportView();
    });
    window.addEventListener("resize", () => {
      const pair = (state.review && Array.isArray(state.review.crosscam_pairs) ? state.review.crosscam_pairs : [])
        .find((item) => item.clip_a + "__" + item.clip_b === state.selectedCrosscamPair);
      if (pair) {
        sizePairVideo(pair.clip_a, "a");
        sizePairVideo(pair.clip_b, "b");
      }
    });
  }

  const demoStages = [
    ["Detect", "Reviewing stored vehicle detections"],
    ["Track", "Following recorded tracks across frames"],
    ["Plate detection", "Locating stored plate observations"],
    ["OCR + fusion", "Replaying stored reads and fused characters"],
    ["Vehicle attributes", "Showing stored type and colour estimates"],
    ["Registry match", "Reviewing stored ranked candidates"],
    ["Report", "Opening the existing report and result"],
  ];

  function populateDemoClips(clips) {
    const select = byId("demo-clip-select");
    if (!select) return;
    const usable = Array.isArray(clips) ? clips.filter((clip) => clip.has_video) : [];
    select.replaceChildren();
    usable.forEach((clip) => {
      const option = document.createElement("option");
      option.value = clip.clip_id;
      option.textContent = clip.clip_id + " · " + formatCameraType(clip.camera_type) + " · " + clip.vehicle_count + " tracked";
      select.appendChild(option);
    });
    if (!usable.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No stored clips with video are available";
      select.appendChild(option);
    } else {
      const preferred = usable.find((clip) => clip.clip_id === "clip03") || usable[0];
      select.value = preferred.clip_id;
    }
    byId("demo-start").disabled = usable.length === 0;
  }

  function renderDemoStages() {
    const run = state.demoRun;
    const list = byId("demo-stage-list");
    list.replaceChildren();
    const complete = Boolean(run && run.complete);
    demoStages.forEach((entry, index) => {
      const item = document.createElement("div");
      const done = complete || (run && index < run.activeIndex);
      const active = !complete && run && index === run.activeIndex;
      item.className = "demo-stage" + (done ? " is-complete" : active ? " is-active" : "");
      if (active) item.setAttribute("aria-current", "step");
      const marker = document.createElement("i");
      marker.textContent = done ? "✓" : String(index + 1).padStart(2, "0");
      const copy = document.createElement("span");
      const title = document.createElement("b");
      title.textContent = entry[0];
      const description = document.createElement("small");
      description.textContent = "SIMULATED · " + entry[1];
      copy.append(title, description);
      item.append(marker, copy);
      list.appendChild(item);
    });
    const completedCount = complete ? demoStages.length : Math.max(0, run ? run.activeIndex : 0);
    setText("demo-progress-count", completedCount + " / " + demoStages.length);
    byId("demo-progress-fill").style.width = complete ? "100%" : run && run.activeIndex >= 0 ? ((run.activeIndex + 0.45) / demoStages.length * 100) + "%" : "0%";
    setText("demo-progress-title", complete ? "Walkthrough ready" : run && run.activeIndex >= 0 ? "Simulating " + demoStages[run.activeIndex][0].toLowerCase() : "Preparing walkthrough");
    byId("demo-complete-message").hidden = !complete;
    byId("demo-open-result").hidden = !complete;
  }

  function advanceDemo(requestId) {
    const run = state.demoRun;
    if (!run || requestId !== state.demoRequestId) return;
    run.activeIndex += 1;
    if (run.activeIndex >= demoStages.length) {
      run.complete = true;
      renderDemoStages();
      return;
    }
    renderDemoStages();
    state.demoTimer = window.setTimeout(() => advanceDemo(requestId), 720);
  }

  function startDemoWalkthrough(clipId) {
    window.clearTimeout(state.demoTimer);
    state.demoTimer = null;
    const requestId = ++state.demoRequestId;
    state.demoRun = { clipId: clipId, activeIndex: -1, complete: false };
    setText("demo-clip-label", "STORED RESULT · " + clipId);
    byId("demo-complete-message").hidden = true;
    byId("demo-open-result").hidden = true;
    renderDemoStages();
    state.demoTimer = window.setTimeout(() => advanceDemo(requestId), 360);
  }

  function showDemoView(clipId) {
    const stored = state.overview && Array.isArray(state.overview.clips)
      ? state.overview.clips.find((clip) => clip.clip_id === clipId && clip.has_video)
      : null;
    if (state.overview && !stored) {
      showLanding();
      showToast("That stored clip is unavailable for demo playback.");
      return;
    }
    state.demoResultClip = null;
    byId("landing-view").hidden = true;
    byId("results-view").hidden = true;
    byId("demo-view").hidden = false;
    ["crosscam-view", "reports-view", "insights-view"].forEach((id) => { byId(id).hidden = true; });
    const resultVideo = byId("result-video");
    if (resultVideo) resultVideo.pause();
    ["pair-video-a", "pair-video-b"].forEach((id) => byId(id).pause());
    setActiveNav("results");
    setText("breadcrumb-current", "Demo mode");
    document.title = "TRACEVISION AI — Demo mode";
    startDemoWalkthrough(clipId);
  }

  function openDemoDialog() {
    populateDemoClips(state.overview && state.overview.clips);
    if (!state.overview) {
      refreshOverview(false).then((data) => { if (data) populateDemoClips(data.clips); });
    }
    const dialog = byId("demo-dialog");
    if (!dialog.open) dialog.showModal();
  }

  function beginDemoFromDialog() {
    const clipId = byId("demo-clip-select").value;
    if (!/^clip\d+$/.test(clipId)) return;
    byId("demo-dialog").close();
    const route = "#demo/" + encodeURIComponent(clipId);
    if (window.location.hash === route) showDemoView(clipId);
    else window.location.hash = route;
  }

  function openDemoResult() {
    const run = state.demoRun;
    if (!run || !run.complete) return;
    window.clearTimeout(state.demoTimer);
    state.demoTimer = null;
    state.demoResultClip = run.clipId;
    window.location.hash = "#results/runs/" + encodeURIComponent(run.clipId);
  }

  function openAboutDialog() {
    const dialog = byId("about-dialog");
    if (!dialog.open) dialog.showModal();
  }

  function commandDefinitions() {
    const commands = [
      { label: "Go to overview", detail: "Workspace home", action: () => { window.location.hash = "#top"; } },
      { label: "Analyse a clip", detail: "Upload a new video", action: () => { window.location.hash = "#upload"; } },
      { label: "Browse stored results", detail: "Open the sample gallery", action: () => { window.location.hash = "#samples-title"; } },
      { label: "Cross-camera review", detail: "Compare stored camera pairs", action: () => { window.location.hash = "#crosscam"; } },
      { label: "Investigation reports", detail: "Preview stored HTML and PDF", action: () => { window.location.hash = "#reports"; } },
      { label: "Evaluation insights", detail: "Metrics and robustness charts", action: () => { window.location.hash = "#insights"; } },
      { label: "Rehearse demo mode", detail: "Run simulated stages on a stored clip", action: openDemoDialog },
      { label: "About and limitations", detail: "Evidence handling and keyboard shortcuts", action: openAboutDialog },
    ];
    const clips = state.overview && Array.isArray(state.overview.clips) ? state.overview.clips : [];
    clips.forEach((clip) => {
      if (!clip.has_video) return;
      commands.push({
        label: "Open result · " + clip.clip_id,
        detail: clip.vehicle_count + " tracked · " + formatCameraType(clip.camera_type),
        action: () => { window.location.hash = "#results/runs/" + encodeURIComponent(clip.clip_id); },
      });
    });
    return commands;
  }

  function renderCommandList(query) {
    const list = byId("command-list");
    list.replaceChildren();
    const normalized = String(query || "").trim().toLowerCase();
    const commands = commandDefinitions().filter((command) => (command.label + " " + command.detail).toLowerCase().includes(normalized));
    state.commandActiveIndex = 0;
    commands.forEach((command, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "command-item";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", index === 0 ? "true" : "false");
      const copy = document.createElement("span");
      copy.className = "command-item-copy";
      const label = document.createElement("b");
      label.textContent = command.label;
      const detail = document.createElement("small");
      detail.textContent = command.detail;
      copy.append(label, detail);
      const arrow = document.createElement("i");
      arrow.textContent = "↗";
      button.append(copy, arrow);
      button.addEventListener("mouseenter", () => setCommandActive(index));
      button.addEventListener("click", () => {
        byId("command-dialog").close();
        command.action();
      });
      list.appendChild(button);
    });
    if (!commands.length) {
      const empty = document.createElement("div");
      empty.className = "command-empty";
      empty.textContent = "No matching commands.";
      list.appendChild(empty);
    }
  }

  function setCommandActive(index) {
    const items = Array.from(byId("command-list").querySelectorAll(".command-item"));
    if (!items.length) return;
    state.commandActiveIndex = (index + items.length) % items.length;
    items.forEach((item, itemIndex) => item.setAttribute("aria-selected", itemIndex === state.commandActiveIndex ? "true" : "false"));
  }

  function openCommandPalette() {
    const dialog = byId("command-dialog");
    byId("command-search").value = "";
    renderCommandList("");
    if (!dialog.open) dialog.showModal();
    window.setTimeout(() => byId("command-search").focus(), 0);
  }

  function runCommandFromPalette() {
    const items = Array.from(byId("command-list").querySelectorAll(".command-item"));
    if (items[state.commandActiveIndex]) items[state.commandActiveIndex].click();
  }

  function navigateShortcut(view) {
    const routes = { o: "#top", c: "#crosscam", i: "#insights", r: "#reports" };
    if (routes[view]) window.location.hash = routes[view];
  }

  function bindPolishControls() {
    byId("demo-mode-open").addEventListener("click", openDemoDialog);
    byId("command-palette-open").addEventListener("click", openCommandPalette);
    byId("about-open").addEventListener("click", openAboutDialog);
    byId("demo-start").addEventListener("click", beginDemoFromDialog);
    byId("demo-open-result").addEventListener("click", openDemoResult);
    byId("demo-exit").addEventListener("click", () => { window.location.hash = "#top"; });
    byId("demo-banner-dismiss").addEventListener("click", () => {
      state.demoResultClip = null;
      byId("demo-result-banner").hidden = true;
    });
    document.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => {
      const dialog = button.closest("dialog");
      if (dialog && dialog.open) dialog.close();
    }));
    ["command-dialog", "demo-dialog", "about-dialog"].forEach((id) => {
      const dialog = byId(id);
      dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
    });
    byId("command-search").addEventListener("input", (event) => renderCommandList(event.target.value));
    byId("command-search").addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") { event.preventDefault(); setCommandActive(state.commandActiveIndex + 1); }
      else if (event.key === "ArrowUp") { event.preventDefault(); setCommandActive(state.commandActiveIndex - 1); }
      else if (event.key === "Enter") { event.preventDefault(); runCommandFromPalette(); }
    });
    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        window.clearTimeout(state.navigationChordTimer);
        state.navigationChordPending = false;
        if (byId("command-dialog").open) byId("command-dialog").close();
        else openCommandPalette();
        return;
      }
      const active = document.activeElement;
      const editing = active && (active.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(active.tagName));
      if (editing || document.querySelector("dialog[open]")) return;
      if (state.navigationChordPending) {
        window.clearTimeout(state.navigationChordTimer);
        state.navigationChordPending = false;
        navigateShortcut(event.key.toLowerCase());
        return;
      }
      if (!event.ctrlKey && !event.altKey && !event.metaKey && event.key.toLowerCase() === "g") {
        state.navigationChordPending = true;
        showToast("Navigation: press O for overview, C for cross-camera, I for insights, or R for reports.");
        window.clearTimeout(state.navigationChordTimer);
        state.navigationChordTimer = window.setTimeout(() => { state.navigationChordPending = false; }, 1400);
      } else if (event.key === "?") {
        event.preventDefault();
        openAboutDialog();
      }
    });
  }

  function bindResultControls() {
    byId("back-to-overview").addEventListener("click", () => { window.location.hash = ""; });
    byId("play-toggle").addEventListener("click", () => {
      const video = byId("result-video");
      if (video.paused) video.play().catch(() => showToast("Video playback could not start."));
      else video.pause();
      updateVideoUI();
    });
    byId("seek-back").addEventListener("click", () => { byId("result-video").currentTime = Math.max(0, byId("result-video").currentTime - 5); });
    byId("seek-forward").addEventListener("click", () => {
      const video = byId("result-video");
      video.currentTime = Math.min(Number.isFinite(video.duration) ? video.duration : video.currentTime + 5, video.currentTime + 5);
    });
    byId("previous-evidence").addEventListener("click", () => {
      const frame = Math.round((Number(byId("result-video").currentTime) || 0) * resultFps(state.result));
      const previous = state.evidenceFrames.filter((item) => item < frame);
      if (previous.length) seekToFrame(previous[previous.length - 1]);
    });
    byId("next-evidence").addEventListener("click", () => {
      const frame = Math.round((Number(byId("result-video").currentTime) || 0) * resultFps(state.result));
      const next = state.evidenceFrames.find((item) => item > frame);
      if (Number.isFinite(next)) seekToFrame(next);
    });
    byId("playback-speed").addEventListener("change", (event) => {
      byId("result-video").playbackRate = Number(event.target.value) || 1;
    });
    byId("seek-slider").addEventListener("input", (event) => {
      const video = byId("result-video");
      const timing = timeFormatFromVideo();
      video.currentTime = (Number(event.target.value) / 1000) * timing.duration;
      updateVideoUI();
    });
    byId("result-video").addEventListener("timeupdate", updateVideoUI);
    byId("result-video").addEventListener("play", updateVideoUI);
    byId("result-video").addEventListener("pause", updateVideoUI);
    byId("track-canvas").addEventListener("click", selectTrackAtPoint);
    window.addEventListener("resize", sizeVideoOverlay);
  }

  bindResultControls();
  bindReviewControls();
  bindPolishControls();
  window.addEventListener("hashchange", handleHashRoute);
  handleHashRoute();
  bindUploadControls();
  refreshOverview(false);
})();
