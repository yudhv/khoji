const audioFile = document.getElementById("audioFile");
const mediaPlayer = document.getElementById("mediaPlayer");
const micButton = document.getElementById("micButton");
const micLabel = document.getElementById("micLabel");
const statusText = document.getElementById("statusText");
const translationLanguage = document.getElementById("translationLanguage");
const emptyState = document.getElementById("emptyState");
const resultView = document.getElementById("resultView");
const unknownView = document.getElementById("unknownView");
const unknownReason = document.getElementById("unknownReason");
const shabadTitle = document.getElementById("shabadTitle");
const shabadDetails = document.getElementById("shabadDetails");
const lineStack = document.getElementById("lineStack");

let recorder = null;
let chunks = [];
let sessionId = makeSessionId();
let selectedMediaFile = null;
let selectedMediaUrl = "";
let mediaTimer = null;
let lastMediaSentAt = 0;
let liveRequestInFlight = false;
let lockedShabadId = "";

const CHUNK_MS = 2000;
const ROLLING_CHUNKS = 5;
const MIN_ROLLING_CHUNKS = 4;
const MEDIA_WINDOW_S = 12;
const MEDIA_HOP_S = 5;
const MIN_MEDIA_WINDOW_S = 8;

audioFile.addEventListener("change", () => {
  const file = audioFile.files?.[0];
  if (!file) return;
  selectMediaFile(file);
});

mediaPlayer.addEventListener("play", () => {
  startMediaClassification();
});

mediaPlayer.addEventListener("pause", () => {
  stopMediaClassification("Paused");
});

mediaPlayer.addEventListener("ended", () => {
  stopMediaClassification("Finished");
});

translationLanguage.addEventListener("change", () => {
  lockedShabadId = "";
  setStatus("Translation changed");
});

micButton.addEventListener("click", async () => {
  if (recorder && recorder.state === "recording") {
    recorder.stop();
    return;
  }

  stopMediaClassification("Media classification paused");
  resetLiveSession();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.addEventListener("dataavailable", async (event) => {
      if (event.data.size === 0 || liveRequestInFlight) return;
      chunks.push(event.data);
      chunks = chunks.slice(-ROLLING_CHUNKS);
      if (chunks.length < MIN_ROLLING_CHUNKS) {
        setStatus(`Collecting ${MIN_ROLLING_CHUNKS * (CHUNK_MS / 1000)}s audio...`);
        return;
      }
      const windowBlob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      await identifyLiveChunk(windowBlob, "live-window.webm", {
        statusPrefix: "Mic",
      });
    });
    recorder.addEventListener("stop", async () => {
      stream.getTracks().forEach((track) => track.stop());
      micButton.classList.remove("recording");
      micButton.setAttribute("aria-pressed", "false");
      micLabel.textContent = "Record";
      setStatus("Stopped");
    });
    recorder.start(CHUNK_MS);
    micButton.classList.add("recording");
    micButton.setAttribute("aria-pressed", "true");
    micLabel.textContent = "Stop";
    setStatus("Listening live...");
  } catch (error) {
    setStatus(`Mic unavailable: ${error.message}`);
  }
});

function selectMediaFile(file) {
  selectedMediaFile = file;
  resetLiveSession();
  stopMediaClassification("Ready");
  if (selectedMediaUrl) URL.revokeObjectURL(selectedMediaUrl);
  selectedMediaUrl = URL.createObjectURL(file);
  mediaPlayer.src = selectedMediaUrl;
  mediaPlayer.hidden = false;
  emptyState.hidden = false;
  resultView.hidden = true;
  unknownView.hidden = true;
  setStatus("Press play to classify media live");
}

function startMediaClassification() {
  if (!selectedMediaFile) return;
  if (recorder && recorder.state === "recording") {
    recorder.stop();
  }
  resetLiveSession();
  lastMediaSentAt = 0;
  setStatus("Listening to media...");
  classifyMediaWindow(true);
  mediaTimer = window.setInterval(() => classifyMediaWindow(false), 1000);
}

function stopMediaClassification(status) {
  if (mediaTimer) {
    window.clearInterval(mediaTimer);
    mediaTimer = null;
  }
  if (status) setStatus(status);
}

async function classifyMediaWindow(force) {
  if (!selectedMediaFile || mediaPlayer.paused || mediaPlayer.ended) return;
  if (liveRequestInFlight) return;

  const currentTime = mediaPlayer.currentTime || 0;
  if (currentTime < MIN_MEDIA_WINDOW_S) {
    setStatus(`Collecting ${Math.ceil(MIN_MEDIA_WINDOW_S - currentTime)}s more audio...`);
    return;
  }
  if (!force && currentTime - lastMediaSentAt < MEDIA_HOP_S) return;

  const duration = Math.min(MEDIA_WINDOW_S, currentTime);
  const start = Math.max(0, currentTime - duration);
  lastMediaSentAt = currentTime;
  await identifyLiveChunk(selectedMediaFile, selectedMediaFile.name || "media", {
    start_s: start,
    duration_s: duration,
    statusPrefix: "Media",
  });
}

async function identifyLiveChunk(blob, filename, options = {}) {
  liveRequestInFlight = true;
  setStatus(`${options.statusPrefix || "Live"} identifying...`);
  const form = new FormData();
  form.append("audio", blob, filename);
  form.append("translation_language", translationLanguage.value);
  form.append("session_id", sessionId);
  if (lockedShabadId) form.append("within_shabad_id", lockedShabadId);
  if (options.start_s !== undefined) form.append("start_s", String(options.start_s));
  if (options.duration_s !== undefined) form.append("duration_s", String(options.duration_s));

  try {
    const response = await fetch("/api/live-chunk", {
      method: "POST",
      body: form,
    });
    const result = await response.json();
    if (!response.ok || result.error) {
      throw new Error(result.error || "Live request failed");
    }
    renderResult(result);
    if (result.live?.status === "holding") {
      setStatus("Holding steady...");
    } else if (result.live?.status === "unknown") {
      setStatus("Listening...");
    } else {
      setStatus(options.statusPrefix ? `${options.statusPrefix} live` : "Live");
    }
  } catch (error) {
    setStatus(`Live chunk failed: ${error.message}`);
  } finally {
    liveRequestInFlight = false;
  }
}

function renderResult(result) {
  if (result.status !== "identified") {
    renderUnknown(result.unknown_reason || "No confident match");
    return;
  }

  lockedShabadId = result.shabad.shabad_id || lockedShabadId;
  emptyState.hidden = true;
  unknownView.hidden = true;
  resultView.hidden = false;
  shabadTitle.textContent = result.shabad.title;
  shabadDetails.textContent = [
    result.shabad.raag,
    result.shabad.author,
    result.shabad.ang ? `Ang ${result.shabad.ang}` : "",
    `Confidence ${Math.round(result.confidence * 100)}%`,
  ].filter(Boolean).join(" · ");

  lineStack.replaceChildren(
    ...result.context_lines.map((line) => {
      const row = document.createElement("div");
      row.className = `line-row${line.is_active ? " active" : ""}`;
      const text = document.createElement("div");
      text.textContent = line.text;
      row.appendChild(text);
      if (line.is_active && line.translation) {
        const translation = document.createElement("div");
        translation.className = "translation";
        translation.textContent = line.translation;
        row.appendChild(translation);
      }
      return row;
    })
  );
}

function renderUnknown(reason) {
  emptyState.hidden = true;
  resultView.hidden = true;
  unknownView.hidden = false;
  unknownReason.textContent = reason;
}

function resetLiveSession() {
  sessionId = makeSessionId();
  chunks = [];
  lockedShabadId = "";
  liveRequestInFlight = false;
}

function setStatus(text) {
  statusText.textContent = text;
}

function makeSessionId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
