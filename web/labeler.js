const labelAudio = document.getElementById("labelAudio");
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

lineSearch.addEventListener("input", () => {
  query = lineSearch.value.trim().toLowerCase();
  renderLines();
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
  labelerTitle.textContent = state.shabad.title;
  labelerMeta.textContent = [
    state.shabad.raag,
    state.shabad.author,
    state.shabad.ang ? `Ang ${state.shabad.ang}` : "",
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
  const lines = state.shabad.lines.filter((line) => {
    if (!query) return true;
    return [
      line.text,
      line.gurmukhi,
      line.punjabi_translation,
      line.english_translation,
      line.section,
    ].join(" ").toLowerCase().includes(query);
  });

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
    subtext.textContent = line.punjabi_translation || line.english_translation || line.section;

    button.append(order, text, subtext);
    return button;
  }));
}

async function startLine(lineId) {
  await postLabel("/api/label-line-click", {
    line_id: lineId,
    time_s: labelAudio.currentTime || 0,
  });
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
    return;
  }
  state = result;
  render();
  setStatus("Saved");
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
