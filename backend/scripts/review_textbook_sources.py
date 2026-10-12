"""Create resumable model observations; never approve or import a directory."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import AppConfig
from services.textbook_source_review import observe_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--concurrency", type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("positive task limit required")
    sources = sorted(args.sources.glob("books/*/front-sources.json"))
    if not args.all:
        sources = sources[:args.limit]
    observe_sources(sources, args.output, AppConfig.from_env(), concurrency=args.concurrency,
                    emit=lambda value: print(json.dumps(value, ensure_ascii=False), flush=True))


if __name__ == "__main__":
    main()
