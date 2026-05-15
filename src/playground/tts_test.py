# scripts/asr_mic.py
import queue
import sys

import sherpa_onnx
import sounddevice as sd

M = "models/sherpa-onnx-streaming-zipformer-en-kroko-2025-08-06"
# M = "models/sherpa-onnx-nemo-streaming-fast-conformer-transducer-en-80ms-int8"
SR = 16000
RESPEAKER_CHANNELS = 6  # v2.0 default firmware: 6ch out
PROCESSED_CH = 0


# Find the ReSpeaker by name; override with --device N if needed.
def find_respeaker():
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] >= 6 and "respeaker" in d["name"].lower():
            return i
    print("ReSpeaker not found. Devices:")
    print(sd.query_devices())
    sys.exit(1)


rec = sherpa_onnx.OnlineRecognizer.from_transducer(
    encoder=f"{M}/encoder.onnx",
    decoder=f"{M}/decoder.onnx",
    joiner=f"{M}/joiner.onnx",
    # encoder=f"{M}/encoder.int8.onnx",
    # decoder=f"{M}/decoder.int8.onnx",
    # joiner=f"{M}/joiner.int8.onnx",
    tokens=f"{M}/tokens.txt",
    # decoding_method="greedy_search",
    decoding_method="modified_beam_search",
    enable_endpoint_detection=True,
    # rule1_min_trailing_silence=2.4,
    # rule2_min_trailing_silence=1.2,
    # rule3_min_utterance_length=20.0,
    rule1_min_trailing_silence=0.5,
    rule2_min_trailing_silence=0.5,
    rule3_min_utterance_length=20.0,
)

stream = rec.create_stream()
q = queue.Queue()


def cb(indata, frames, t, status):
    if status:
        print(status, file=sys.stderr)
    # indata shape: (frames, 6) float32 — take ch0 only
    q.put(indata[:, PROCESSED_CH].copy())


device = find_respeaker()
print(f"Using device {device}: {sd.query_devices(device)['name']}")

with sd.InputStream(
    device=device, channels=RESPEAKER_CHANNELS, samplerate=SR, dtype="float32", blocksize=1600, callback=cb
):  # 100 ms blocks
    last = ""
    while True:
        chunk = q.get()
        stream.accept_waveform(SR, chunk)
        while rec.is_ready(stream):
            rec.decode_stream(stream)
        text = rec.get_result(stream)
        if text and text != last:
            print(f"\r{text}", end="", flush=True)
            last = text
        if rec.is_endpoint(stream):
            if text.strip():
                print(f"\n→ FINAL: {text}")
            rec.reset(stream)
            last = ""
