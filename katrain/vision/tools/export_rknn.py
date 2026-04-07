"""Export YOLO ONNX model to RKNN format for Rockchip NPU inference.

Usage:
    python -m katrain.vision.tools.export_rknn --onnx best.onnx --target rk3576
    python -m katrain.vision.tools.export_rknn --onnx best.onnx --target rk3576 --quantize --dataset calibration.txt

Requires: rknn-toolkit2 (x86 only — cannot run on ARM boards).
Install via: pip install rknn-toolkit2
Or use the Docker image from airockchip/rknn-toolkit2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SUPPORTED_TARGETS = ["rk3562", "rk3566", "rk3568", "rk3576", "rk3588"]


def export_rknn(
    onnx_path: str,
    target: str = "rk3576",
    output_dir: str | None = None,
    quantize: bool = False,
    dataset: str | None = None,
) -> Path:
    """Convert an ONNX YOLO model to RKNN format.

    Args:
        onnx_path: Path to the ``.onnx`` model file (must have a ``.meta.json`` sidecar).
        target: Rockchip target platform (e.g. ``rk3576``, ``rk3588``).
        output_dir: Directory for output files.  Defaults to same directory as ONNX model.
        quantize: Whether to apply INT8 quantization (requires ``dataset``).
        dataset: Path to calibration dataset text file (one image path per line).
            Required when ``quantize=True``.

    Returns:
        Path to the exported ``.rknn`` file.
    """
    try:
        from rknn.api import RKNN
    except ImportError:
        print(
            "Error: rknn-toolkit2 is required for RKNN export (x86 only).\n"
            "Install with: pip install rknn-toolkit2\n"
            "Or use Docker: https://github.com/airockchip/rknn-toolkit2"
        )
        sys.exit(1)

    onnx_file = Path(onnx_path)
    if not onnx_file.is_file():
        raise FileNotFoundError(f"ONNX model not found: {onnx_file}")

    # Load ONNX metadata sidecar
    onnx_meta_file = onnx_file.with_suffix(".meta.json")
    if not onnx_meta_file.is_file():
        raise FileNotFoundError(
            f"ONNX metadata sidecar not found: {onnx_meta_file}. "
            "Export one first with: python -m katrain.vision.tools.export_onnx"
        )

    with open(onnx_meta_file, "r") as f:
        onnx_meta = json.load(f)

    if target not in SUPPORTED_TARGETS:
        raise ValueError(f"Unsupported target: {target!r}. Choose from: {SUPPORTED_TARGETS}")

    if quantize and dataset is None:
        raise ValueError("INT8 quantization requires --dataset with calibration image paths")

    if output_dir:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = onnx_file.parent

    imgsz = onnx_meta.get("imgsz", 640)
    classes = onnx_meta.get("classes", ["black", "white"])

    # --- Downgrade ONNX opset if needed (rknn-toolkit2 requires <= 19) ---
    MAX_OPSET = 19
    onnx_load_path = str(onnx_file)
    try:
        import onnx
        from onnx import version_converter

        model = onnx.load(onnx_load_path)
        current_opset = model.opset_import[0].version
        if current_opset > MAX_OPSET:
            print(f"ONNX opset {current_opset} > {MAX_OPSET}, downgrading...")
            converted = version_converter.convert_version(model, MAX_OPSET)
            tmp_path = str(out_dir / f"{onnx_file.stem}_opset{MAX_OPSET}.onnx")
            onnx.save(converted, tmp_path)
            onnx_load_path = tmp_path
            print(f"Saved opset-{MAX_OPSET} model: {tmp_path}")
    except Exception as e:
        print(f"Warning: opset check/conversion failed ({e}), trying original model")

    # --- RKNN conversion ---
    rknn = RKNN()

    # Bake normalization into the model: uint8 [0,255] -> float32 [0,1]
    # mean=[0,0,0] std=[255,255,255] is equivalent to dividing by 255
    print(f"Configuring RKNN for target={target}, imgsz={imgsz}, quantize={quantize}")
    rknn.config(
        mean_values=[[0, 0, 0]],
        std_values=[[255, 255, 255]],
        target_platform=target,
    )

    print(f"Loading ONNX model: {onnx_load_path}")
    ret = rknn.load_onnx(model=onnx_load_path)
    if ret != 0:
        raise RuntimeError(f"Failed to load ONNX model (error code: {ret})")

    print(f"Building RKNN model (quantize={quantize})...")
    ret = rknn.build(do_quantization=quantize, dataset=dataset)
    if ret != 0:
        raise RuntimeError(f"Failed to build RKNN model (error code: {ret})")

    # Output filename: {stem}_{target}.rknn
    rknn_filename = f"{onnx_file.stem}_{target}.rknn"
    rknn_path = out_dir / rknn_filename

    print(f"Exporting RKNN model: {rknn_path}")
    ret = rknn.export_rknn(str(rknn_path))
    if ret != 0:
        raise RuntimeError(f"Failed to export RKNN model (error code: {ret})")

    rknn.release()

    # --- Generate RKNN metadata sidecar ---
    rknn_meta = {
        "format": "rknn",
        "source": onnx_meta.get("source", onnx_file.stem),
        "source_onnx": onnx_file.name,
        "target_platform": target,
        "imgsz": imgsz,
        "input_format": "nhwc_uint8",
        "input_channel_order": "RGB",
        "output_format": onnx_meta.get("output_format", "yolo_v8_raw"),
        "output_shape": onnx_meta.get("output_shape"),
        "classes": classes,
        "includes_nms": False,
        "bbox_format": "xywh_center_normalized",
        "quantized": quantize,
    }

    meta_path = rknn_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(rknn_meta, indent=2, ensure_ascii=False))

    print(f"\nExport complete:")
    print(f"  RKNN model:  {rknn_path}")
    print(f"  Metadata:    {meta_path}")
    print(f"  Target:      {target}")
    print(f"  Classes:     {classes}")
    print(f"  Input:       NHWC uint8 {imgsz}x{imgsz} (normalization baked in)")
    print(f"  Quantized:   {quantize}")

    return rknn_path


def main():
    parser = argparse.ArgumentParser(description="Export YOLO ONNX model to RKNN format for Rockchip NPU")
    parser.add_argument("--onnx", required=True, help="Path to .onnx model file")
    parser.add_argument("--target", default="rk3576", choices=SUPPORTED_TARGETS, help="Target platform (default: rk3576)")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: same as ONNX model)")
    parser.add_argument("--quantize", action="store_true", help="Apply INT8 quantization (requires --dataset)")
    parser.add_argument(
        "--dataset",
        default=None,
        help="Path to calibration dataset text file (one image path per line). Required for --quantize.",
    )
    args = parser.parse_args()

    export_rknn(
        onnx_path=args.onnx,
        target=args.target,
        output_dir=args.output_dir,
        quantize=args.quantize,
        dataset=args.dataset,
    )


if __name__ == "__main__":
    main()
