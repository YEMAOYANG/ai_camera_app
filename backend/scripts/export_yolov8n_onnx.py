#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


def main() -> int:
    backend_root = Path(__file__).resolve().parents[1]
    output_dir = backend_root / "assets" / "vision"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "yolov8n.onnx"

    from ultralytics import YOLO

    model = YOLO("yolov8n.pt")
    exported = model.export(format="onnx", simplify=True, imgsz=640, opset=12)
    exported_path = Path(str(exported)).resolve()
    if exported_path != output_path.resolve():
        output_path.write_bytes(exported_path.read_bytes())
        if exported_path.parent == backend_root and exported_path.name == output_path.name:
            exported_path.unlink(missing_ok=True)
    print(f"exported {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
