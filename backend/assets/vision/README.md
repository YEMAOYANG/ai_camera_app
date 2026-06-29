# Vision prefilter assets

Guardian observation worker requires both OpenCV motion prefilter and YOLOv8n person
detection. The ONNX model must exist before the worker starts.

## Shipped model

`yolov8n.onnx` is tracked in git under this directory. After clone, worker startup
should find `assets/vision/yolov8n.onnx` relative to `backend/`.

## Regenerate (optional)

```sh
cd backend
pip install ultralytics
python scripts/export_yolov8n_onnx.py
```

This writes `backend/assets/vision/yolov8n.onnx` (ONNX opset 12, compatible with onnxruntime 1.19.x).

`start-dev.sh` will attempt a one-time export when the file is missing and ultralytics is installed.

## Production

Ship `yolov8n.onnx` with the backend image. Override path via `APP_PREFILTER_MODEL` if needed.
