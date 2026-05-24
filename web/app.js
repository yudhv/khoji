const audioFile = document.getElementById("audioFile");
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

audioFile.addEventListener("change", async () => {
  const file = audioFile.files?.[0];
  if (!file) return;
  await identifyAudio(file);
});

micButton.addEventListener("click", async () => {
  if (recorder && recorder.state === "recording") {
    recorder.stop();
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    });
    recorder.addEventListener("stop", async () => {
      stream.getTracks().forEach((track) => track.stop());
      micButton.classList.remove("recording");
      micButton.setAttribute("aria-pressed", "false");
      micLabel.textContent = "Record";
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      await identifyAudio(blob);
    });
    recorder.start();
    micButton.classList.add("recording");
    micButton.setAttribute("aria-pressed", "true");
    micLabel.textContent = "Stop";
    setStatus("Recording...");
  } catch (error) {
    setStatus(`Mic unavailable: ${error.message}`);
  }
});

async function identifyAudio(blob) {
  setStatus("Identifying...");
  const form = new FormData();
  form.append("audio", blob, "clip.webm");
  form.append("translation_language", translationLanguage.value);

  try {
    const response = await fetch("/api/identify-audio", {
      method: "POST",
      body: form,
    });
    const result = await response.json();
    if (!response.ok || result.error) {
      throw new Error(result.error || "Request failed");
    }
    renderResult(result);
  } catch (error) {
    renderUnknown(error.message);
  }
}

function renderResult(result) {
  if (result.status !== "identified") {
    renderUnknown(result.unknown_reason || "No confident match");
    return;
  }

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
  setStatus("Identified");
}

function renderUnknown(reason) {
  emptyState.hidden = true;
  resultView.hidden = true;
  unknownView.hidden = false;
  unknownReason.textContent = reason;
  setStatus("Not confident yet");
}

function setStatus(text) {
  statusText.textContent = text;
}

