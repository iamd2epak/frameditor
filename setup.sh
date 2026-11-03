#!/usr/bin/env bash
# One-time setup (safe to re-run). Needs: python3 (3.10+), ffmpeg, curl.
set -e
cd "$(dirname "$0")"
pip install -q -r requirements.txt --break-system-packages 2>/dev/null || pip install -q -r requirements.txt
mkdir -p models reels out
[ -s models/kokoro-v1.0.onnx ] || curl -sSL -o models/kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
[ -s models/voices-v1.0.bin ]  || curl -sSL -o models/voices-v1.0.bin  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
command -v ffmpeg >/dev/null || echo "WARNING: ffmpeg not found - install it (apt install ffmpeg / brew install ffmpeg)"
echo "setup ok"
