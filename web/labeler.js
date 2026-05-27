const labelAudio = document.getElementById("labelAudio");
const mediaFile = document.getElementById("mediaFile");
const labelerTitle = document.getElementById("labelerTitle");
const labelerMeta = document.getElementById("labelerMeta");
const currentTime = document.getElementById("currentTime");
const activeLabel = document.getElementById("activeLabel");
const finishButton = document.getElementById("finishButton");
const resetButton = document.getElementById("resetButton");
const lineSearch = document.getElementById("lineSearch");
const lineList = document.getElementById("lineList");
const segmentList = document.getElementById("segmentList");
const labelStatus = document.getElementById("labelStatus");

const params = new URLSearchParams(window.location.search);
let recordingId = params.get("recording_id") || "kahe_re_ban_full_001";
let state = null;
let query = "";
let searchResults = [];
let searchLoading = false;
let searchTimer = null;

lineSearch.addEventListener("input", () => {
  query = lineSearch.value.trim();
  if (!query) {
    searchResults = [];
    searchLoading = false;
    renderLines();
    setStatus("Ready");
    return;
  }
  if (compactQueryLength(query) < 3) {
    searchResults = [];
    searchLoading = false;
    renderLines();
    setStatus("Type at least 3 characters");
    return;
  }
  searchLoading = true;
  renderLines();
  setStatus("Searching SGGS...");
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(searchCanonicalLines, 220);
});

mediaFile.addEventListener("change", async () => {
  const file = mediaFile.files?.[0];
  if (!file) return;
  await uploadRecording(file);
});

labelAudio.addEventListener("timeupdate", () => {
  currentTime.textContent = formatClock(labelAudio.currentTime || 0);
});

finishButton.addEventListener("click", async () => {
  await postLabel("/api/label-finish", { time_s: labelAudio.currentTime || 0 });
});

resetButton.addEventListener("click", async () => {
  if (!window.confirm("Reset labels for this recording?")) return;
  await postLabel("/api/label-reset", {});
});

loadState();

async function loadState() {
  setStatus("Loading...");
  const response = await fetch(`/api/labeler-state?recording_id=${encodeURIComponent(recordingId)}`);
  const payload = await response.json();
  if (!response.ok || payload.error) {
    throw new Error(payload.error || "Could not load labeler");
  }
  state = payload;
  recordingId = state.recording.recording_id;
  labelAudio.src = state.recording.audio_url;
  labelerTitle.textContent = state.shabad?.title || "Search SGGS to choose a line";
  labelerMeta.textContent = [
    state.shabad?.raag,
    state.shabad?.author,
    state.shabad?.ang ? `Ang ${state.shabad.ang}` : "",
    state.recording.recording_id,
  ].filter(Boolean).join(" · ");
  render();
  setStatus("Ready");
}

function render() {
  renderLines();
  renderSegments();
}

function renderLines() {
  if (!state) return;
  const activeLineId = currentOpenSegment()?.line_id || "";
  const usingSearch = Boolean(query);
  const lines = usingSearch ? searchResults : (state.shabad?.lines || []);

  if (usingSearch && compactQueryLength(query) < 3) {
    const hint = document.createElement("p");
    hint.className = "segment-empty";
    hint.textContent = "Type at least 3 characters";
    lineList.replaceChildren(hint);
    return;
  }

  if (usingSearch && searchLoading) {
    const loading = document.createElement("p");
    loading.className = "segment-empty";
    loading.textContent = "Searching SGGS...";
    lineList.replaceChildren(loading);
    return;
  }

  if (usingSearch && lines.length === 0) {
    const empty = document.createElement("p");
    empty.className = "segment-empty";
    empty.textContent = "No matching lines";
    lineList.replaceChildren(empty);
    return;
  }

  if (!usingSearch && lines.length === 0) {
    const empty = document.createElement("p");
    empty.className = "segment-empty";
    empty.textContent = "Search SGGS to choose the first line";
    lineList.replaceChildren(empty);
    return;
  }

  lineList.replaceChildren(...lines.map((line) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `label-line${line.line_id === activeLineId ? " active" : ""}`;
    button.addEventListener("click", () => startLine(line.line_id));

    const order = document.createElement("div");
    order.className = "label-line-order";
    order.textContent = `${line.order}`;

    const text = document.createElement("div");
    text.className = "label-line-text";
    text.textContent = line.text;

    const subtext = document.createElement("div");
    subtext.className = "label-line-subtext";
    subtext.textContent = usingSearch
      ? [
          line.shabad_title,
          line.ang ? `Ang ${line.ang}` : "",
          line.punjabi_translation || line.english_translation || line.section,
        ].filter(Boolean).join(" · ")
      : line.punjabi_translation || line.english_translation || line.section;

    button.append(order, text, subtext);
    return button;
  }));
}

function compactQueryLength(value) {
  return value.replace(/\s+/g, "").length;
}

async function searchCanonicalLines() {
  const currentQuery = query;
  if (!currentQuery) return;
  try {
    const response = await fetch(`/api/search-lines?q=${encodeURIComponent(currentQuery)}&top_k=30`);
    const payload = await response.json();
    if (!response.ok || payload.error) {
      throw new Error(payload.error || "Search failed");
    }
    if (currentQuery !== query) return;
    searchResults = payload.results || [];
    searchLoading = false;
    renderLines();
    setStatus("Ready");
  } catch (error) {
    if (currentQuery !== query) return;
    searchResults = [];
    searchLoading = false;
    renderLines();
    setStatus(error.message);
  }
}

async function startLine(lineId) {
  const wasSearching = Boolean(query);
  const saved = await postLabel("/api/label-line-click", {
    line_id: lineId,
    time_s: labelAudio.currentTime || 0,
  });
  if (saved && wasSearching) {
    query = "";
    searchResults = [];
    searchLoading = false;
    lineSearch.value = "";
    renderLines();
  }
}

async function postLabel(path, payload) {
  setStatus("Saving...");
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recording_id: recordingId, ...payload }),
  });
  const result = await response.json();
  if (!response.ok || result.error) {
    setStatus(result.error || "Save failed");
    return false;
  }
  state = result;
  labelerTitle.textContent = state.shabad?.title || "Search SGGS to choose a line";
  labelerMeta.textContent = [
    state.shabad?.raag,
    state.shabad?.author,
    state.shabad?.ang ? `Ang ${state.shabad.ang}` : "",
    state.recording.recording_id,
  ].filter(Boolean).join(" · ");
  render();
  setStatus("Saved");
  return true;
}

async function uploadRecording(file) {
  setStatus("Uploading...");
  const form = new FormData();
  form.append("audio", file, file.name);
  const response = await fetch("/api/recording-upload", {
    method: "POST",
    body: form,
  });
  const result = await response.json();
  if (!response.ok || result.error) {
    setStatus(result.error || "Upload failed");
    return;
  }
  state = result;
  recordingId = state.recording.recording_id;
  query = "";
  searchResults = [];
  searchLoading = false;
  lineSearch.value = "";
  labelAudio.src = state.recording.audio_url;
  labelerTitle.textContent = state.shabad?.title || "Search SGGS to choose a line";
  labelerMeta.textContent = state.recording.recording_id;
  window.history.replaceState(null, "", `/labeler?recording_id=${encodeURIComponent(recordingId)}`);
  render();
  setStatus("Ready");
}

function renderSegments() {
  if (!state) return;
  const labels = state.labels || [];
  const open = currentOpenSegment();
  activeLabel.textContent = open
    ? `Active: ${open.text}`
    : "No active segment";

  if (labels.length === 0) {
    const empty = document.createElement("p");
    empty.className = "segment-empty";
    empty.textContent = "No segments yet";
    segmentList.replaceChildren(empty);
    return;
  }

  segmentList.replaceChildren(...labels.map((label, index) => {
    const item = document.createElement("div");
    item.className = `segment-item${label.end_s ? "" : " open"}`;

    const time = document.createElement("div");
    time.className = "segment-time";
    time.textContent = `${label.start_s || "?"} -> ${label.end_s || "open"}`;

    const text = document.createElement("div");
    text.className = "segment-text";
    text.textContent = `${index + 1}. ${label.text || label.segment_type}`;

    item.append(time, text);
    return item;
  }));
}

function currentOpenSegment() {
  const labels = state?.labels || [];
  const last = labels[labels.length - 1];
  return last && !last.end_s ? last : null;
}

function setStatus(text) {
  labelStatus.textContent = text;
}

function formatClock(seconds) {
  const minutes = Math.floor(seconds / 60);
  const wholeSeconds = Math.floor(seconds % 60);
  const millis = Math.floor((seconds % 1) * 1000);
  return `${String(minutes).padStart(2, "0")}:${String(wholeSeconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}
