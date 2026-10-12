"""Prepare or dispatch exact-source DeepSeek teaching designs; never publish."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.textbook_deepseek_authoring import DeepSeekTextbookAuthoring, read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dispatch", action="store_true")
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--concurrency", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    if not 1 <= args.limit <= 24:
        parser.error("limit must be 1..24")
    index = read(args.index)
    if index.get("schemaVersion") not in {"mira.textbook.deepseek-instruction-index.v1",
                                         "mira.textbook.deepseek-instruction-revision-index.v1",
                                         "mira.textbook.deepseek-instruction-patch-index.v1"}:
        parser.error("exact-source authoring index required")
    service = DeepSeekTextbookAuthoring(args.output)
    if index["schemaVersion"] == "mira.textbook.deepseek-instruction-patch-index.v1":
        folders = [service.prepare_patch(entry["parentDirectory"], entry["reviewPath"])
                   for entry in index["entries"][:args.limit]]
    elif index["schemaVersion"] == "mira.textbook.deepseek-instruction-revision-index.v1":
        folders = [service.prepare_revision(entry["parentDirectory"], entry["reviewPath"])
                   for entry in index["entries"][:args.limit]]
    else:
        folders = [service.prepare(entry["taskPath"], entry["scopePath"],
                    pictures_path=entry.get("picturesPath"), gap_path=entry.get("gapPath"))
                   for entry in index["entries"][:args.limit]]
    for folder in folders:
        print(json.dumps({"status": "prepared", "requestDirectory": str(folder)}, ensure_ascii=False), flush=True)
    if args.dispatch:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            for result in as_completed([pool.submit(service.run, folder) for folder in folders]):
                print(json.dumps(result.result(), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
