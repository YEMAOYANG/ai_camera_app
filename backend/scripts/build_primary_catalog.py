from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import AppConfig
from services.dynamic_learning_course_generation_service import (
    DynamicLearningCourseGenerationService,
)
from services.learning_catalog_release_service import LearningCatalogReleaseService
from services.lesson_package_service import LessonPackageService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create, resume, inspect, or activate a Mira primary catalog release."
    )
    parser.add_argument("--request-id", help="Idempotency id for a new build")
    parser.add_argument("--build-id", help="Existing build to resume or inspect")
    parser.add_argument("--release-id", help="Existing release to activate")
    parser.add_argument("--grade", action="append", dest="grades")
    parser.add_argument(
        "--subject",
        action="append",
        choices=("chinese", "math", "english"),
        dest="subjects",
    )
    parser.add_argument("--variants", type=int, default=1)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--max-items", type=int, default=1)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--retry-external",
        action="store_true",
        help="Explicitly replay a quota/transport failure with the same logical attempt",
    )
    parser.add_argument(
        "--use-generation-feedback",
        action="store_true",
        help="Explicitly send the prior safe course-validation failure to the model on retry",
    )
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args(argv)

    config = AppConfig.from_env()
    config.validate()
    lesson_service = LessonPackageService(config.DATABASE_URL)
    dynamic_service = DynamicLearningCourseGenerationService(
        config.DATABASE_URL,
        classroom_enqueue=lesson_service.enqueue,
    )
    service = LearningCatalogReleaseService(
        config.DATABASE_URL,
        dynamic_generation_service=dynamic_service,
        lesson_package_service=lesson_service,
    )

    if args.release_id and args.activate:
        payload = service.activate(args.release_id)
    elif args.build_id and args.run:
        payload = service.run(
            args.build_id,
            {
                "maxItems": args.max_items,
                "retryFailed": args.retry_failed,
                "retryExternal": args.retry_external,
                "useGenerationFeedback": args.use_generation_feedback,
            },
        )
    elif args.build_id:
        payload = service.status(args.build_id)
    elif args.request_id:
        payload = service.create(
            {
                "requestId": args.request_id,
                "grades": args.grades,
                "subjects": args.subjects,
                "variantsPerBoundary": args.variants,
                "allowPartial": args.allow_partial,
            }
        )
        if args.run:
            payload = service.run(
                payload["build"]["id"],
                {
                    "maxItems": args.max_items,
                    "retryFailed": args.retry_failed,
                    "retryExternal": args.retry_external,
                    "useGenerationFeedback": args.use_generation_feedback,
                },
            )
        if args.activate and payload.get("canActivate"):
            payload = service.activate(payload["release"]["id"])
    else:
        parser.error("provide --request-id, --build-id, or --release-id --activate")

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
