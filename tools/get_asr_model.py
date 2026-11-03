#!/usr/bin/env python3
"""Download the offline ASR model used to time custom voice files word by word (models/parakeet).
NeMo Parakeet TDT 0.6B v2 (int8) for sherpa-onnx, ~650 MB, from the k2-fsa/sherpa-onnx GitHub releases.

  python tools/get_asr_model.py
"""
import os, shutil, subprocess, sys, tarfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(ROOT, "models", "parakeet")
NAME = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{NAME}.tar.bz2"


def main():
    if os.path.exists(os.path.join(DST, "encoder.int8.onnx")): print("asr model ok"); return
    try: import sherpa_onnx  # noqa
    except ImportError: subprocess.run([sys.executable, "-m", "pip", "install", "-q", "sherpa-onnx", "--break-system-packages"], check=True)
    tmp = os.path.join(ROOT, "models", NAME + ".tar.bz2"); os.makedirs(os.path.dirname(tmp), exist_ok=True)
    print("downloading ASR model (~650 MB, once)…", flush=True)
    subprocess.run(["curl", "-sSL", "-o", tmp, URL], check=True)
    with tarfile.open(tmp) as t: t.extractall(os.path.join(ROOT, "models"), filter="data")
    os.remove(tmp); src = os.path.join(ROOT, "models", NAME)
    os.makedirs(DST, exist_ok=True)
    for f in ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"): shutil.move(os.path.join(src, f), os.path.join(DST, f))
    shutil.rmtree(src, ignore_errors=True); print("asr model ok")


if __name__ == "__main__": main()
