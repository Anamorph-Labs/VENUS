"""Local speech-to-text with OpenAI Whisper (MIT) run through onnxruntime.

No PyTorch, no API keys, no network at run time. The model files are the
ONNX export from https://huggingface.co/onnx-community/whisper-base.en and
are downloaded once by `alvenus fetch-models` (or by hand) into a cache dir.

This file holds our own small implementation of Whisper's audio front end
(log-mel spectrogram) and a greedy decoder, so the only Python dependencies
are numpy and onnxruntime.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
N_FFT = 400
HOP = 160
N_MELS = 80
CHUNK_SAMPLES = 30 * SAMPLE_RATE  # Whisper always looks at a 30 s window

MODEL_REPO = "onnx-community/whisper-base.en"
MODEL_FILES = [
    "onnx/encoder_model.onnx",
    "onnx/decoder_model.onnx",
    "vocab.json",
    "added_tokens.json",
    "generation_config.json",
]


def default_model_dir() -> Path:
    base = os.environ.get("ALVENUS_MODELS") or os.path.join(
        os.path.expanduser("~"), ".cache", "al-venus"
    )
    return Path(base) / "whisper-base.en"


# --------------------------------------------------------------------------
# Audio front end
# --------------------------------------------------------------------------

def _hz_to_mel(f):
    """Slaney mel scale (same as librosa's default, which Whisper uses)."""
    f = np.asarray(f, dtype=np.float64)
    f_sp = 200.0 / 3
    mels = f / f_sp
    min_log_hz = 1000.0
    min_log_mel = min_log_hz / f_sp
    logstep = np.log(6.4) / 27.0
    return np.where(f >= min_log_hz, min_log_mel + np.log(np.maximum(f, 1e-10) / min_log_hz) / logstep, mels)


def _mel_to_hz(m):
    m = np.asarray(m, dtype=np.float64)
    f_sp = 200.0 / 3
    freqs = f_sp * m
    min_log_hz = 1000.0
    min_log_mel = min_log_hz / f_sp
    logstep = np.log(6.4) / 27.0
    return np.where(m >= min_log_mel, min_log_hz * np.exp(logstep * (m - min_log_mel)), freqs)


@lru_cache(maxsize=1)
def mel_filters() -> np.ndarray:
    fft_freqs = np.linspace(0, SAMPLE_RATE / 2, 1 + N_FFT // 2)
    mel_pts = _mel_to_hz(np.linspace(_hz_to_mel(0.0), _hz_to_mel(SAMPLE_RATE / 2), N_MELS + 2))
    fdiff = np.diff(mel_pts)
    ramps = mel_pts[:, None] - fft_freqs[None, :]
    weights = np.zeros((N_MELS, len(fft_freqs)))
    for i in range(N_MELS):
        lower = -ramps[i] / fdiff[i]
        upper = ramps[i + 2] / fdiff[i + 1]
        weights[i] = np.maximum(0, np.minimum(lower, upper))
    enorm = 2.0 / (mel_pts[2 : N_MELS + 2] - mel_pts[:N_MELS])
    weights *= enorm[:, None]
    return weights.astype(np.float32)


def log_mel(audio: np.ndarray) -> np.ndarray:
    """80 x 3000 log-mel features for one 30 s window (pads or trims)."""
    audio = np.asarray(audio, dtype=np.float32)
    if len(audio) > CHUNK_SAMPLES:
        audio = audio[:CHUNK_SAMPLES]
    audio = np.pad(audio, (0, CHUNK_SAMPLES - len(audio)))
    padded = np.pad(audio, (N_FFT // 2, N_FFT // 2), mode="reflect")
    window = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)
    n_frames = 1 + (len(padded) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    frames = padded[idx] * window
    power = np.abs(np.fft.rfft(frames, axis=1)) ** 2  # (frames, 201)
    power = power[:-1]  # Whisper drops the last frame -> 3000
    mel = mel_filters() @ power.T.astype(np.float32)
    logm = np.log10(np.maximum(mel, 1e-10))
    logm = np.maximum(logm, logm.max() - 8.0)
    return ((logm + 4.0) / 4.0).astype(np.float32)


# --------------------------------------------------------------------------
# Tokenizer (byte-level BPE, decode only)
# --------------------------------------------------------------------------

def _byte_decoder() -> dict[str, int]:
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return {chr(c): b for b, c in zip(bs, cs)}


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

@dataclass
class Transcript:
    text: str
    avg_logprob: float  # mean log-probability of the chosen tokens (higher = surer)


class Whisper:
    def __init__(self, model_dir: str | Path | None = None, threads: int | None = None):
        import onnxruntime as ort

        d = Path(model_dir) if model_dir else default_model_dir()
        missing = [f for f in MODEL_FILES if not (d / Path(f).name).exists()]
        if missing:
            raise FileNotFoundError(
                f"Whisper model files missing in {d}: {missing}. Run `python -m alvenus fetch-models`."
            )
        opts = ort.SessionOptions()
        if threads:
            opts.intra_op_num_threads = threads
        self.enc = ort.InferenceSession(str(d / "encoder_model.onnx"), opts, providers=["CPUExecutionProvider"])
        self.dec = ort.InferenceSession(str(d / "decoder_model.onnx"), opts, providers=["CPUExecutionProvider"])
        vocab = json.loads((d / "vocab.json").read_text())
        vocab.update(json.loads((d / "added_tokens.json").read_text()))
        self.id_to_tok = {v: k for k, v in vocab.items()}
        gen = json.loads((d / "generation_config.json").read_text())
        self.sot = gen["decoder_start_token_id"]
        self.eot = gen["eos_token_id"]
        self.no_ts = gen["no_timestamps_token_id"]
        self.suppress = np.array(gen["suppress_tokens"], dtype=np.int64)
        self.begin_suppress = np.array(gen["begin_suppress_tokens"], dtype=np.int64)
        self.byte_dec = _byte_decoder()

    def _detok(self, ids: list[int]) -> str:
        text = "".join(self.id_to_tok.get(i, "") for i in ids if i < self.eot)
        return bytearray(self.byte_dec[c] for c in text if c in self.byte_dec).decode("utf-8", errors="replace").strip()

    def transcribe(self, audio: np.ndarray, max_tokens: int = 200, prompt: str | None = None) -> Transcript:
        """Greedy decode of one clip (<= 30 s) of 16 kHz mono float audio."""
        feats = log_mel(audio)[None]
        hidden = self.enc.run(None, {"input_features": feats})[0]
        tokens = [self.sot, self.no_ts]
        out: list[int] = []
        logps: list[float] = []
        for step in range(max_tokens):
            logits = self.dec.run(
                ["logits"],
                {"input_ids": np.array([tokens], dtype=np.int64), "encoder_hidden_states": hidden},
            )[0][0, -1].astype(np.float64)
            logits[self.suppress] = -np.inf
            if step == 0:
                logits[self.begin_suppress] = -np.inf
            # timestamp and other special tokens are never wanted here
            logits[self.eot + 1 :] = -np.inf
            m = logits.max()
            logprobs = logits - (m + np.log(np.exp(logits - m).sum()))
            nxt = int(np.argmax(logits))
            if nxt == self.eot:
                break
            # stop runaway repetition loops (a known Whisper failure)
            if len(out) >= 12 and out[-6:] == out[-12:-6]:
                break
            out.append(nxt)
            logps.append(float(logprobs[nxt]))
            tokens.append(nxt)
        avg = float(np.mean(logps)) if logps else -10.0
        return Transcript(self._detok(out), avg)


def fetch_models(model_dir: str | Path | None = None) -> Path:
    """Download the Whisper ONNX files from Hugging Face (free, one time)."""
    import urllib.request

    d = Path(model_dir) if model_dir else default_model_dir()
    d.mkdir(parents=True, exist_ok=True)
    for f in MODEL_FILES:
        dest = d / Path(f).name
        if dest.exists() and dest.stat().st_size > 0:
            continue
        url = f"https://huggingface.co/{MODEL_REPO}/resolve/main/{f}"
        print(f"downloading {url}")
        tmp = dest.with_suffix(dest.suffix + ".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.rename(dest)
    return d
