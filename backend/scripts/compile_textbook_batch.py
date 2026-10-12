#!/usr/bin/env python3
"""Compile bounded, frozen private courseware locally; never dispatch a Provider.

Single input: --input --input-sha256 --design --design-sha256
--source-scope-sha256 --media-sha256 --output-directory.
Batch: --index (schema mira.textbook.activity-compiler-batch.v1, entries use
the same exact hashes and absolute paths), optionally --task-id/--limit.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content.textbook_activity_ir import FAMILIES, require
from services.textbook_activity_compiler import compile_batch, preflight


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--index", type=Path)
    p.add_argument("--input", type=Path)
    p.add_argument("--input-sha256")
    p.add_argument("--design", type=Path)
    p.add_argument("--design-sha256")
    p.add_argument("--source-scope-sha256")
    p.add_argument("--media-sha256")
    p.add_argument("--recipe", type=Path)
    p.add_argument("--recipe-byte-sha256")
    p.add_argument("--output-directory", type=Path)
    p.add_argument("--task-id", action="append", default=[])
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--check", action="store_true", help="Validate all selected contracts; create no files")
    p.add_argument("--describe", action="store_true", help="Print supported families and scope; create no files")
    args = p.parse_args(argv)
    try:
        if args.describe:
            print(json.dumps({"supportedKinds": ["book_exploration", "unit_guide"], "families": FAMILIES,
                "lessonSemanticsSupported": False, "arbitraryHTMLOrJavascriptAccepted": False,
                "providerCalls": 0, "publicationAllowed": False}, ensure_ascii=False))
            return 0
        require(1 <= args.limit <= 128, "limit_must_be_1_to_128")
        if args.index:
            require(not any((args.input, args.input_sha256, args.design, args.design_sha256,
                             args.source_scope_sha256, args.media_sha256, args.recipe, args.recipe_byte_sha256)), "index_or_single_input_required")
            value = json.loads(args.index.read_text())
            require(isinstance(value, dict) and set(value) == {"schemaVersion", "entries"}
                    and value["schemaVersion"] == "mira.textbook.activity-compiler-batch.v1"
                    and isinstance(value["entries"], list) and value["entries"], "batch_index_invalid")
            entries = value["entries"]
            if args.task_id:
                selected = set(args.task_id)
                # Input is checked again with exact hash, so identity selection cannot bypass preflight.
                entries = [e for e in entries if json.loads(Path(e["inputPath"]).read_text()).get("taskId") in selected]
                require(len(entries) == len(selected), "requested_task_missing_or_duplicate")
            entries = entries[:args.limit]
        else:
            require(args.input and args.design and not args.task_id, "single_input_and_design_required")
            entry = {"inputPath": str(args.input), "inputSha256": args.input_sha256,
                     "designPath": str(args.design), "activityDesignSha256": args.design_sha256,
                     "sourceScopeSha256": args.source_scope_sha256, "providedMediaSha256": args.media_sha256}
            if args.recipe:
                entry.update(recipePath=str(args.recipe), recipeByteSha256=args.recipe_byte_sha256)
            else:
                require(not args.recipe_byte_sha256, "recipe_path_missing")
            entries = [entry]
        if args.check:
            checked = [preflight(e) for e in entries]
            result = [{"taskId": item[0]["taskId"], "modelAdapterKey": item[3]["modelAdapterKey"],
                       "sourceScopeSha256": item[3]["sourceScopeSha256"], "providerCalls": 0,
                       "contractValid": True, "semanticTeachingReview": "pending", "browserQAPassed": False} for item in checked]
        else:
            require(args.output_directory is not None, "output_directory_required")
            result = compile_batch(entries, args.output_directory)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if args.check or all(r["structuralChecksPassed"] for r in result) else 2
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
