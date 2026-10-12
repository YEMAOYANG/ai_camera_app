"""Collect exact public textbook sources with durable per-page resume receipts."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.textbook_source_acquisition import TextbookSourceAcquisition


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("front", "declared-pages"), default="front")
    parser.add_argument("--edition", action="append")
    parser.add_argument("--subject", choices=("chinese", "math", "english", "science"))
    parser.add_argument("--missing-directories", action="store_true")
    parser.add_argument("--all", action="store_true", help="Process the full exact selected catalog")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--concurrency", type=int, choices=range(1, 5), default=3)
    parser.add_argument("--front-pages", type=int, choices=range(1, 13), default=8)
    parser.add_argument("--maximum-mib", type=int, default=2048)
    args = parser.parse_args()
    if args.limit < 1 or not 1 <= args.maximum_mib <= 8192:
        parser.error("positive bounded byte budget and task limit required")
    tasks = [json.loads(line) for line in args.plan.read_text().splitlines()]
    tasks = [t for t in tasks if t["kind"] == "book_exploration"]
    if args.subject:
        tasks = [t for t in tasks if t['scope']['subject'] == args.subject]
    tasks.sort(key=lambda t: (t['scope']['gradeCode'], t['scope']['schoolSystem'] != 'six_year', t['scope']['volume'] != 'upper', t['scope']['editionId']))
    if args.edition:
        tasks = [t for t in tasks if t["scope"]["editionId"] in set(args.edition)]
        if {t["scope"]["editionId"] for t in tasks} != set(args.edition):
            raise ValueError("edition_not_in_exact_plan")
    if args.missing_directories:
        tasks = [t for t in tasks if json.loads(Path(t["sourcePaths"][0]).read_text())["coverage"]["status"] != "complete"]
    if not args.all:
        tasks = tasks[:args.limit]
    service = TextbookSourceAcquisition(args.output, maximum_bytes=args.maximum_mib * 1024**2)
    service.run(tasks, mode=args.mode, front_pages=args.front_pages, concurrency=args.concurrency,
                emit=lambda value: print(json.dumps(value, ensure_ascii=False), flush=True))


if __name__ == "__main__":
    main()
