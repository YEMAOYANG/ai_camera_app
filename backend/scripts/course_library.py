"""Inspect/request shared coverage, or run an explicitly bounded local canary."""
from __future__ import annotations

import argparse
import fcntl
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import AppConfig
from core.security import now_ms
from repositories.course_supply_repository import observe_supply_incidents
from services.course_library_service import CourseLibraryService


def emit(event, **data):
    print(json.dumps({'event': event, **data}, ensure_ascii=False, default=str), flush=True)


def all_canaries_settled(status):
    items = status.get('items', [])
    return len(items) == 3 and all(
        item.get('ready') or (
            item.get('reason_code') and item.get('runtime_status') != 'generating'
        ) for item in items
    )


def check_research_dependency(client, policy):
    query = policy['dependencyPreflight']['searchQuery']
    # The existing search endpoint only invokes its query-rewrite model for
    # queries over 400 characters or PDF input. Keep this a search-only check.
    if not isinstance(query, str) or not query.strip() or len(query) > 120:
        raise ValueError('invalid research preflight query')
    try:
        result = client._request_json('POST', '/api/web-search', body={'query': query}, timeout_seconds=20)
    except Exception as exc:
        return {'ready': False, 'reasonCode': 'research_rate_limited' if '429' in str(exc)
                else 'research_unavailable', 'message': '联网检索暂不可用，尚未启动模型生成。'}
    sources = result.get('sources', []) if isinstance(result, dict) else []
    ready = isinstance(sources, list) and any(isinstance(source, dict)
                and isinstance(source.get('url'), str)
                and source['url'].startswith(('https://', 'http://')) for source in sources)
    return {'ready': ready, 'reasonCode': None if ready else 'research_empty',
            'message': '联网检索检查通过。' if ready else '联网检索未返回可用资料，尚未启动模型生成。'}


def assert_budget(conn, build_id, max_courses):
    rows = conn.execute(
        """SELECT item.id, COUNT(DISTINCT dispatch.id) AS calls,
          COUNT(DISTINCT runtime.id) AS attempts
        FROM learning_catalog_build_items AS item
        LEFT JOIN learning_course_provider_dispatches AS dispatch ON dispatch.build_item_id = item.id
        LEFT JOIN learning_openmaic_runtime_classrooms AS runtime ON runtime.candidate_build_item_id = item.id
        WHERE item.build_job_id = ? GROUP BY item.id""", (build_id,),
    ).fetchall()
    touched = [r for r in rows if r['calls'] or r['attempts']]
    if len(touched) > max_courses or any(r['calls'] > 14 or r['attempts'] > 3 for r in rows):
        raise RuntimeError('existing production exceeds the approved scope or attempt ceiling')


def unblock_known_retry(library, item_id):
    """One explicit retry of the exact known rejection; retain its evidence."""
    with library.database.transaction() as conn:
        owner = conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE library_target_fingerprint = ? FOR UPDATE', (library.fingerprint,)).fetchone()
        if not owner or not owner['catalog_build_id']:
            raise RuntimeError('library has no build')
        observe_supply_incidents(conn, build_id=owner['catalog_build_id'], now=now_ms())
        latest = conn.execute(
            """SELECT runtime.* FROM learning_openmaic_runtime_classrooms AS runtime
            JOIN learning_catalog_build_items AS item ON item.id = runtime.candidate_build_item_id
            JOIN learning_course_supply_requests AS request ON request.target_fingerprint = runtime.candidate_target_fingerprint
              AND request.subject = item.subject AND request.skill_id = item.skill_id
              AND request.variant_ordinal = item.variant_ordinal AND request.enabled = TRUE
            WHERE item.id = ? AND item.build_job_id = ? ORDER BY runtime.created_at DESC, runtime.id DESC LIMIT 1 FOR UPDATE""",
            (item_id, owner['catalog_build_id']),
        ).fetchone()
        if not latest or latest['status'] != 'failed' or latest['quality_status'] != 'rejected' or not latest['upstream_job_id'] or latest['retired_at'] is not None:
            raise RuntimeError('retry requires an exact, known terminal rejection')
        code = str(latest['error_code'] or '')
        if not code.startswith('openmaic_formal_') or 'ambiguous' in code:
            raise RuntimeError('uncertain failures are never automatically replayed')
        conn.execute(
            'UPDATE learning_course_supply_incidents SET resolved_at = ? WHERE build_item_id = ? AND failure_runtime_id = ? AND resolved_at IS NULL',
            (now_ms(), item_id, latest['id']),
        )
        emit('retry_unblocked', buildItemId=item_id, predecessorRuntimeId=latest['id'])


def run_canaries(args):
    from scripts.generate_one_formal_course import _operator_app, LOCK_PATH
    from services.learning_curriculum_preparation_runner import learning_curriculum_preparation_runner
    from services.service_factory import learning_curriculum_preparation_checkpoint_adapter, openmaic_full_runtime_service

    if args.confirm_paid_canaries is not True:
        raise RuntimeError('--confirm-paid-canaries is required for real generation')
    app = _operator_app()
    app.config.update(LEARNING_COURSE_LIBRARY_ENABLED=True, LEARNING_COURSE_SUPPLY_SCOPE='canary',
                      LEARNING_CURRICULUM_PREPARATION_PROGRESSIVE_PUBLICATION_LIMIT=3)
    with LOCK_PATH.open('a') as lock, app.app_context():
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        library = CourseLibraryService(app.config['DATABASE_URL'], preparation_repository=learning_curriculum_preparation_checkpoint_adapter().repository)
        library.request_scope('canary')
        owner = library.ensure_owner()
        if owner.get('catalog_build_id'):
            with library.database.transaction() as conn:
                assert_budget(conn, owner['catalog_build_id'], 3)
        runtime = openmaic_full_runtime_service()
        if library.status()['readyCount'] == 3:
            emit('ready', library=library.status())
            return 0
        dependency = check_research_dependency(runtime.client, library.policy)
        emit('dependency_preflight', **dependency)
        if not dependency['ready']:
            raise RuntimeError('research dependency is unavailable; no model generation was started')
        if args.probe_provider:
            probe = runtime.probe_formal_generation_provider()
            emit('provider_probe', ready=probe.get('ready'), dispatchAllowed=probe.get('dispatchAllowed'))
        if not runtime.formal_provider_circuit_status()['dispatchAllowed']:
            raise RuntimeError('provider is blocked; inspect status before an explicitly authorized probe')
        if args.retry_item:
            unblock_known_retry(library, args.retry_item)
        deadline = time.monotonic() + args.timeout_seconds
        next_runtime_poll = 0
        observed = None
        while time.monotonic() < deadline:
            status = library.status()
            if status['readyCount'] == 3:
                emit('ready', library=status)
                return 0
            if all_canaries_settled(status):
                emit('review_required', ready=status['readyCount'], requested=3,
                     items=[{key: item.get(key) for key in ('subject', 'ready', 'reason_code')}
                            for item in status['items']])
                return 1
            if status['state'] in {'failed', 'superseded'}:
                raise RuntimeError('library ownership or build requires review')
            owner = library.ensure_owner()
            if owner.get('catalog_build_id'):
                with library.database.transaction() as conn:
                    assert_budget(conn, owner['catalog_build_id'], 3)
                    pending = conn.execute("SELECT upstream_job_id FROM learning_openmaic_runtime_classrooms WHERE candidate_target_fingerprint = ? AND status = 'generating'", (library.fingerprint,)).fetchall()
                if time.monotonic() >= next_runtime_poll:
                    for row in pending:
                        if row['upstream_job_id']:
                            runtime.generation_status(row['upstream_job_id'])
                    next_runtime_poll = time.monotonic() + 5
            if not runtime.formal_provider_circuit_status()['dispatchAllowed']:
                raise RuntimeError('provider circuit opened; no further production was dispatched')
            tick = learning_curriculum_preparation_runner.run_once(app, now_ms=now_ms())
            observation = (status['readyCount'], status['lastProgressAt'], status['blocked'],
                           tuple((item.get('subject'), item.get('runtime_status'), item.get('reason_code'))
                                 for item in status['items']))
            if observation != observed:
                emit('progress', ready=status['readyCount'], requested=3, blocked=status['blocked'], tick=tick)
                observed = observation
            time.sleep(1.25)
        raise RuntimeError('operator deadline reached; persisted checkpoints retained')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    sub.add_parser('check-dependencies', help='check configured research search without starting course production')
    prepare = sub.add_parser('prepare', help='persist desired scope only; makes no model calls')
    prepare.add_argument('--scope', choices=('canary', 'first_unit', 'catalog'), required=True)
    run = sub.add_parser('run-canaries', help='at most the three subject entry courses')
    run.add_argument('--confirm-paid-canaries', action='store_true')
    run.add_argument('--probe-provider', action='store_true')
    run.add_argument('--retry-item', help='explicitly unblock the exact known failed item once')
    run.add_argument('--timeout-seconds', type=int, default=1800, choices=range(1, 3601), metavar='1..3600')
    args = parser.parse_args()
    try:
        if args.command == 'run-canaries':
            return run_canaries(args)
        if args.command == 'check-dependencies':
            from scripts.generate_one_formal_course import _operator_app
            from services.service_factory import openmaic_full_runtime_service
            app = _operator_app()
            with app.app_context():
                library = CourseLibraryService(app.config['DATABASE_URL'])
                result = check_research_dependency(openmaic_full_runtime_service().client, library.policy)
                emit('dependency_preflight', **result)
                return 0 if result['ready'] else 1
        library = CourseLibraryService(AppConfig.from_env().DATABASE_URL)
        if args.command == 'prepare':
            emit('requested', **library.request_scope(args.scope))
        else:
            emit('status', library=library.status())
        return 0
    except Exception as exc:
        # Known local errors only; do not dump credentials or provider bodies.
        emit('stopped', reason=str(exc) if isinstance(exc, (RuntimeError, ValueError)) else type(exc).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
