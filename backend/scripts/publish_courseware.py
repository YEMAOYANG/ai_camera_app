#!/usr/bin/env python3
"""Check or publish light courseware locally; registration is a separate step."""
import argparse
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
for directory in (BACKEND, ROOT):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check')
    check.add_argument('--lesson-dir', required=True)
    check.add_argument('--json', action='store_true')
    publish = commands.add_parser('publish')
    publish.add_argument('--lesson-dir', required=True)
    publish.add_argument('--owner-quote', required=True)
    publish.add_argument('--confirmed-at', required=True)
    publish.add_argument('--author-attestation', required=True)
    publish.add_argument('--apply', action='store_true')
    status = commands.add_parser('status')
    status.add_argument('--classroom-id', required=True)
    args = parser.parse_args(argv)
    from core.errors import ApiError
    from services.courseware_publish_service import CoursewarePublishService
    try:
        # An embedded manifest lets check run without configuration or a DB.
        identity = json.loads((Path(args.lesson_dir) / 'identity.json').read_text()) if args.command == 'check' else {}
        if args.command == 'check' and identity.get('manifest'):
            service = CoursewarePublishService(None, classroom_directory=ROOT / 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms')
        else:
            from core.config import AppConfig
            from core.database import Database
            from repositories.textbook_repository import TextbookRepository
            config = AppConfig.from_env()
            service = CoursewarePublishService(TextbookRepository(Database(config.DATABASE_URL)),
                classroom_directory=ROOT / 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms')
        if args.command == 'check':
            report = service.check(args.lesson_dir)
            value = {key: item for key, item in report.items() if key != 'prepared'}
        elif args.command == 'publish':
            value = service.publish(args.lesson_dir, apply=args.apply, confirmation={
                'userQuote': args.owner_quote, 'confirmedAt': args.confirmed_at,
                'confirmedBy': 'owner', 'authorAttestation': args.author_attestation})
        else:
            value = service.status(classroom_id=args.classroom_id)
    except ApiError as exc:
        value = {'ok': False, 'errors': [exc.code]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        value = {'ok': False, 'errors': [str(exc)]}
    if args.command != 'check' or args.json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        print('PASS G0-G8' if value['ok'] else 'FAIL: ' + '; '.join(value['errors']))
        for issue in value.get('issues', []):
            print('{gate} {severity} {code}: {detail}'.format(**issue))
    return 0 if value.get('ok', True) else 1


if __name__ == '__main__':
    raise SystemExit(main())
