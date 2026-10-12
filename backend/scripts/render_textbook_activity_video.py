#!/usr/bin/env python3
"""Render create-only, silent original SVG component animation. No API calls.

Run under tools/task_tmp.py so rasterization work is confined and cleaned.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.textbook_activity_video import preflight_video, render_video
from content.textbook_activity_ir import require


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path)
    parser.add_argument("--task-sha256")
    parser.add_argument("--design", type=Path)
    parser.add_argument("--design-sha256")
    parser.add_argument("--index", type=Path)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    require(1 <= args.limit <= 32, "video_limit_must_be_1_to_32")
    if args.index:
        require(not any((args.task, args.task_sha256, args.design, args.design_sha256)), "video_index_or_single_required")
        value = json.loads(args.index.read_text())
        require(isinstance(value, dict) and set(value) == {"schemaVersion", "entries"}
                and value["schemaVersion"] == "mira.textbook.original-video-batch.v1"
                and isinstance(value["entries"], list) and value["entries"], "video_batch_index_invalid")
        entries = value["entries"][:args.limit]
    else:
        require(args.task and args.design and args.task_sha256 and args.design_sha256, "video_explicit_task_and_design_required")
        entries = [{"taskPath": str(args.task), "taskSha256": args.task_sha256,
                    "designPath": str(args.design), "designSha256": args.design_sha256}]
    require(all(isinstance(e, dict) and set(e) == {"taskPath", "taskSha256", "designPath", "designSha256"} for e in entries), "video_batch_entry_invalid")
    contracts = [preflight_video(e["taskPath"], e["designPath"], task_sha256=e["taskSha256"], design_sha256=e["designSha256"]) for e in entries]
    require(len({c["task"]["taskId"] for c in contracts}) == len(contracts), "video_duplicate_batch_task")
    if args.check:
        result = [{"taskId": c["task"]["taskId"], "animationFamily": c["plan"]["animationFamily"], "contractValid": True} for c in contracts]
    else:
        if args.output_directory is None:
            parser.error("--output-directory is required for rendering")
        result = []
        for entry in entries:
            receipt = render_video(entry["taskPath"], entry["designPath"], args.output_directory,
                task_sha256=entry["taskSha256"], design_sha256=entry["designSha256"])
            result.append({"taskId": receipt["taskId"], "status": receipt["status"],
                "videoPath": receipt["video"]["path"], "videoSha256": receipt["video"]["sha256"],
                "receiptPath": str(Path(receipt["video"]["path"]).parent / "local-render-receipt.json"),
                "providerCalls": 0, "runtimeCalls": 0, "publicationAllowed": False})
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
