from __future__ import annotations

import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


DEFAULT_SURT_MODEL_ID = "surindersinghssj/surt-small-v3"


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    model: str
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AudioTranscriber(Protocol):
    def transcribe_bytes(self, audio_bytes: bytes) -> TranscriptionResult:
        ...


class SurtSmallV3Transcriber:
    """Lazy wrapper around the Surt Whisper-small Gurbani ASR model."""

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_SURT_MODEL_ID,
        device: str | int | None = None,
        chunk_length_s: int = 30,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.chunk_length_s = chunk_length_s
        self._pipeline: Any | None = None

    def transcribe_bytes(self, audio_bytes: bytes) -> TranscriptionResult:
        if not audio_bytes:
            raise ValueError("Cannot transcribe empty audio")

        started = time.perf_counter()
        with tempfile.TemporaryDirectory() as directory:
            wav_path = Path(directory) / "audio-16khz-mono.wav"
            _write_wav_16khz_mono(audio_bytes, wav_path)
            result = self._load_pipeline()(
                str(wav_path),
                generate_kwargs={"language": "punjabi", "task": "transcribe"},
            )

        text = str(result.get("text", "") if isinstance(result, dict) else result).strip()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return TranscriptionResult(
            text=text,
            model=self.model_id,
            metadata={
                "elapsed_ms": elapsed_ms,
                "chunk_length_s": self.chunk_length_s,
            },
        )

    def _load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline

        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError(
                "Surt ASR requires optional dependencies. Install them with "
                "`python3 -m pip install -e '.[asr]'`."
            ) from exc

        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "chunk_length_s": self.chunk_length_s,
        }
        if self.device is not None:
            kwargs["device"] = self.device
        self._pipeline = pipeline("automatic-speech-recognition", **kwargs)
        return self._pipeline


def build_audio_transcriber(
    name: str,
    *,
    model_id: str = DEFAULT_SURT_MODEL_ID,
    device: str | int | None = None,
    chunk_length_s: int = 30,
) -> AudioTranscriber | None:
    if name in {"", "none"}:
        return None
    if name == "surt-small-v3":
        return SurtSmallV3Transcriber(
            model_id=model_id,
            device=device,
            chunk_length_s=chunk_length_s,
        )
    raise ValueError(f"Unknown ASR model: {name}")


def extract_audio_window(
    audio_bytes: bytes,
    *,
    start_s: float | None = None,
    duration_s: float | None = None,
) -> bytes:
    if start_s is None and duration_s is None:
        return audio_bytes
    if start_s is not None and start_s < 0:
        raise ValueError("--start-s must be >= 0")
    if duration_s is not None and duration_s <= 0:
        raise ValueError("--duration-s must be > 0")

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
    ]
    if start_s is not None:
        command.extend(["-ss", str(start_s)])
    if duration_s is not None:
        command.extend(["-t", str(duration_s)])
    command.extend(["-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1"])
    try:
        completed = subprocess.run(
            command,
            input=audio_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is required for audio window extraction") from exc
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"ffmpeg could not extract audio window: {error}")
    return completed.stdout


def _write_wav_16khz_mono(audio_bytes: bytes, wav_path: Path) -> None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(wav_path),
    ]
    try:
        completed = subprocess.run(
            command,
            input=audio_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is required for audio transcription") from exc
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"ffmpeg could not decode audio: {error}")
