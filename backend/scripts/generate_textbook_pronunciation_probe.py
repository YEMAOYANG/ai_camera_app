"""Prepare, run, inspect and review the bounded Garden 4 pronunciation probes.

``prepare`` and ``status`` never construct a provider client.  ``run`` is the
only paid/network action and requires a sealed authorization for the exact
four-call plan.  The runner persists each intent before its one allowed POST.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.errors import ApiError  # noqa: E402
from services.textbook_pronunciation_probe_generation import (  # noqa: E402
    PronunciationProbeError,
    build_operator_review,
    prepare,
    run,
    status,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)

    prepare_parser = commands.add_parser("prepare", help="write the canonical four-call plan and requests; no network")
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument("--edition-id", required=True)
    prepare_parser.add_argument("--alignment-revision-id", required=True)
    prepare_parser.add_argument("--node-id", required=True)
    prepare_parser.add_argument("--grade-code", required=True)
    prepare_parser.add_argument("--subject", required=True)
    prepare_parser.add_argument("--teaching-revision", required=True)

    run_parser = commands.add_parser("run", help="make each authorized paid POST at most once")
    run_parser.add_argument("--output-dir", type=Path, required=True)
    run_parser.add_argument("--dispatch-authorization", type=Path, required=True)

    review_parser = commands.add_parser(
        "review", help="build protocol/WAV-only operator-probe-review.json; never claims human listening")
    review_parser.add_argument("--output-dir", type=Path, required=True)
    review_parser.add_argument("--review-context", type=Path, required=True)

    status_parser = commands.add_parser("status", help="inspect local artifacts; no network")
    status_parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "prepare":
            result = prepare(args.output_dir, {
                "editionId": args.edition_id,
                "revisionId": args.alignment_revision_id,
                "nodeId": args.node_id,
                "gradeCode": args.grade_code,
                "subject": args.subject,
                "teachingRevision": args.teaching_revision,
            })
        elif args.action == "run":
            result = run(args.output_dir, args.dispatch_authorization)
        elif args.action == "review":
            result = build_operator_review(args.output_dir, args.review_context)
        else:
            result = status(args.output_dir)
    except (PronunciationProbeError, ApiError, OSError, ValueError) as exc:
        print(json.dumps({"error": getattr(exc, "code", "pronunciation_probe_io_error"),
                          "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
