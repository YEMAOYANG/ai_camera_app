"""Plan/apply one original draft's completion credential, without Provider calls."""
import argparse
import json
from pathlib import Path
import sys
import time

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from content.learning_budget_policy import LearningBudgetPolicy
from core.config import AppConfig
from core.database import Database
from services.learning_budget_service import LearningBudgetService
from services.learning_saved_stage_tail_authorization import plan_tail_authorization, apply_tail_authorization, _archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('plan', 'apply'))
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-job', type=Path)
    parser.add_argument('--source-snapshot', type=Path)
    parser.add_argument('--prepared-snapshot', type=Path)
    parser.add_argument('--starts-at', type=int)
    parser.add_argument('--expires-at', type=int)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--expected-plan-sha')
    parser.add_argument('--sidecar-output', type=Path)
    args = parser.parse_args()
    source_args = (args.source_job, args.source_snapshot, args.prepared_snapshot, args.starts_at, args.expires_at)
    if args.mode == 'plan':
        if not all(value is not None for value in source_args) or args.plan or args.expected_plan_sha or args.sidecar_output:
            parser.error('plan requires original source-job/source-snapshot/prepared-snapshot and explicit starts/expires only')
    elif not (args.plan and args.expected_plan_sha and args.sidecar_output) or any(value is not None for value in source_args):
        parser.error('apply requires the reviewed plan, expected-plan-sha and sidecar-output only')
    config = AppConfig.from_env()
    budget = LearningBudgetService(Database(config.DATABASE_URL), policy=LearningBudgetPolicy.load(args.policy),
                                    clock=lambda: int(time.time() * 1000))
    if args.mode == 'plan':
        result = plan_tail_authorization(budget=budget, source_job_path=args.source_job,
            source_snapshot_path=args.source_snapshot, prepared_snapshot_path=args.prepared_snapshot,
            starts_at=args.starts_at, expires_at=args.expires_at)
    else:
        document = json.loads(args.plan.read_bytes())
        result = apply_tail_authorization(budget=budget, plan=document['plan'], expected_plan_sha=args.expected_plan_sha)
    # Create-only local output. A repeated apply returns the exact DB proof and
    # cannot mint another authority or send a Provider request.
    _archive(args.output.resolve(), result)
    if args.sidecar_output:
        _archive(args.sidecar_output.resolve(), result['sidecar'])
    print(json.dumps({'applied': result['applied'], 'planSha256': result['planSha256'],
                      'authorizationId': result['sidecar']['authorizationId'],
                      'output': str(args.output.resolve()), 'providerCalls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
