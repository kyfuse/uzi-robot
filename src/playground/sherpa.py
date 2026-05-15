# scripts/asr_test.py
import sys
import time

import sherpa_onnx
import soundfile as sf

ROOT = "models"

MODELS = {
    "fast-conformer-80ms": {
        "dir": "sherpa-onnx-nemo-streaming-fast-conformer-transducer-en-80ms-int8",
        "enc": "encoder.int8.onnx",
        "dec": "decoder.int8.onnx",
        "join": "joiner.int8.onnx",
    },
    "zipformer-06-26": {
        "dir": "sherpa-onnx-streaming-zipformer-en-2023-06-26",
        "enc": "encoder-epoch-99-avg-1-chunk-16-left-128.onnx",
        "dec": "decoder-epoch-99-avg-1-chunk-16-left-128.onnx",
        "join": "joiner-epoch-99-avg-1-chunk-16-left-128.onnx",
    },
    "kroko": {
        "dir": "sherpa-onnx-streaming-zipformer-en-kroko-2025-08-06",
        "enc": "encoder.onnx",
        "dec": "decoder.onnx",
        "join": "joiner.onnx",
    },
    "nemotron-0.6b-80ms": {
        "dir": "sherpa-onnx-nemotron-speech-streaming-en-0.6b-80ms-int8-2026-04-25",
        "enc": "encoder.int8.onnx",
        "dec": "decoder.int8.onnx",
        "join": "joiner.int8.onnx",
    },
}


def transcribe(name, cfg, audio, sr):
    M = f"{ROOT}/{cfg['dir']}"
    rec = sherpa_onnx.OnlineRecognizer.from_transducer(
        encoder=f"{M}/{cfg['enc']}",
        decoder=f"{M}/{cfg['dec']}",
        joiner=f"{M}/{cfg['join']}",
        tokens=f"{M}/tokens.txt",
        decoding_method="greedy_search",
    )
    start_time = time.time()
    s = rec.create_stream()
    s.accept_waveform(sr, audio)
    s.input_finished()
    while rec.is_ready(s):
        rec.decode_stream(s)
    end_time = time.time()
    return rec.get_result(s), end_time - start_time


audio, sr = sf.read(sys.argv[1], dtype="float32")
if audio.ndim > 1:
    audio = audio.mean(axis=1)

print(f"Input: {sys.argv[1]} ({len(audio)/sr:.2f}s @ {sr}Hz)\n")
for name, cfg in MODELS.items():
    try:
        text, duration = transcribe(name, cfg, audio, sr)
        print(f"{name:25s} → {text} ({duration:.2f}s)")
    except Exception as e:
        print(f"{name:25s} ✗ {type(e).__name__}: {e}")
