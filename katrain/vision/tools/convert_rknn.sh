#!/usr/bin/env bash
# Convert YOLO ONNX model to RKNN format using Docker.
#
# Usage:
#   ./katrain/vision/tools/convert_rknn.sh
#   ./katrain/vision/tools/convert_rknn.sh --onnx katrain/vision/models/yolo11s/best.onnx --target rk3588
#   ./katrain/vision/tools/convert_rknn.sh --onnx best.onnx --target rk3576 --quantize --dataset calibration.txt
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
IMAGE_NAME="katrain-rknn-toolkit2"

# Defaults
ARGS=("$@")
if [ ${#ARGS[@]} -eq 0 ]; then
    ARGS=(--onnx katrain/vision/models/yolo11n/best.onnx --target rk3576)
    echo "No arguments provided. Using defaults: ${ARGS[*]}"
fi

# Build Docker image (cached after first run)
echo "Building Docker image (platform: linux/amd64)..."
docker build \
    --platform linux/amd64 \
    -t "$IMAGE_NAME" \
    -f "$SCRIPT_DIR/Dockerfile.rknn" \
    "$SCRIPT_DIR"

echo "Running RKNN conversion..."
docker run --rm \
    --platform linux/amd64 \
    -v "$PROJECT_ROOT:/work" \
    "$IMAGE_NAME" \
    "${ARGS[@]}"
