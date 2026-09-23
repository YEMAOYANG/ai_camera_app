"""Validate/import an explicit manifest or reserve one original authoring input.

Does not download textbooks, migrate a database, call a provider or publish.
Run from the repository root: python backend/scripts/textbooks.py --help
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content.textbook_catalog import authoring_prompt, digest, generation_brief, validate_manifest
from core.errors import ApiError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "validate-catalog", "export-brief", "import", "import-catalog", "prepare"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--node")
    parser.add_argument("--teaching-revision", default="1")
    parser.add_argument("--part", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        bulk = args.action in {"validate-catalog", "import-catalog"}
        paths = sorted(args.manifest.glob("*.json")) if bulk else [args.manifest]
        if not paths or len(paths) > 500:
            raise ApiError("textbook_catalog_invalid", "没有找到有效的教材清单文件", 400)
        manifests = [validate_manifest(json.loads(path.read_text(encoding="utf-8"))) for path in paths]
        if len({(m["editionId"], m["revisionId"]) for m in manifests}) != len(manifests):
            raise ApiError("textbook_catalog_invalid", "目录包含重复的教材修订", 400)
        manifest = manifests[0]
        if args.action == "validate":
            result = {"ok": True, "editionId": manifest["editionId"], "revisionId": manifest["revisionId"],
                      "manifestSha256": digest(manifest), "coverage": manifest["coverage"],
                      "lessonCount": sum(len(u["lessons"]) for u in manifest["units"]),
                      "rightsReviewStatus": manifest["rightsReview"]["status"]}
        elif args.action == "validate-catalog":
            result = {"ok": True, "bookCount": len(manifests),
                      "coverageCounts": {status: sum(m["coverage"]["status"] == status for m in manifests)
                                         for status in ("index_only", "partial", "complete")},
                      "books": [{"editionId": m["editionId"], "revisionId": m["revisionId"],
                                 "manifestSha256": digest(m)} for m in manifests], "providerDispatched": False}
        elif args.action == "export-brief":
            result = {"generationInput": generation_brief(manifest, args.node, teaching_revision=args.teaching_revision, part_index=args.part),
                      "prompt": authoring_prompt(), "providerDispatched": False}
        else:
            # Configuration is loaded only for explicitly requested database work.
            from core.config import AppConfig
            from core.database import Database
            from repositories.textbook_repository import TextbookRepository
            from services.textbook_learning_service import TextbookLearningService
            config = AppConfig.from_env()
            service = TextbookLearningService(TextbookRepository(Database(config.DATABASE_URL)))
            if args.action == "import-catalog":
                result = service.import_catalog(manifests)
            elif args.action == "import":
                result = service.import_manifest(manifest)
            else:
                if not args.node:
                    parser.error("prepare requires --node")
                # No implicit import/update: prepare uses the reviewed DB revision.
                with service.repository.transaction() as conn:
                    row = service.repository.get_revision(conn, manifest["editionId"], manifest["revisionId"])
                    if row is None or row["manifest_sha256"] != digest(manifest):
                        raise ApiError("textbook_revision_conflict", "先导入相同摘要的教材修订", 409)
                result = service.prepare({"editionId": manifest["editionId"], "alignmentRevisionId": manifest["revisionId"],
                                          "nodeId": args.node, "teachingRevision": args.teaching_revision, "partIndex": args.part})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ApiError, ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": getattr(exc, "code", "textbook_input_invalid"),
                          "message": getattr(exc, "message", "无法读取有效的教材 JSON")}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
