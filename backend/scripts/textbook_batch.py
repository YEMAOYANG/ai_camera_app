"""Write a read-only textbook audit and blocked authoring backlog; no providers or DB."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content.textbook_batch import build_plan, write_plan
from core.errors import ApiError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "content/textbooks")
    parser.add_argument("--output", type=Path, required=True, help="Create-only summary.json and tasks.jsonl directory")
    parser.add_argument("--include-superseded", action="store_true", help="Audit retired choices too; never changes parent choices")
    args = parser.parse_args(argv)
    try:
        summary, tasks = build_plan(args.catalog, include_superseded=args.include_superseded)
        files = write_plan(args.output, summary, tasks)
    except (ApiError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": getattr(exc, "code", "textbook_batch_invalid"),
                          "message": getattr(exc, "message", str(exc)), "providerDispatched": False}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "counts": summary["counts"], "planSha256": summary["planSha256"],
                      "files": files, "executionReady": False, "providerDispatched": False, "published": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
