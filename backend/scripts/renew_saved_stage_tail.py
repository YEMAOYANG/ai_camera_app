"""Review/apply one completion window renewal; no Provider calls or new grant."""
import argparse
import json
from pathlib import Path
import sys
import time

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from content.learning_budget_policy import LearningBudgetPolicy
from core.config import AppConfig
from core.database import Database
from services.learning_budget_service import LearningBudgetService
from services.learning_saved_stage_tail_authorization import plan_tail_renewal, apply_tail_renewal, _archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('plan', 'apply'))
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expires-at', type=int)
    parser.add_argument('--approval-reference')
    parser.add_argument('--approval-text')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--expected-plan-sha')
    parser.add_argument('--sidecar-output', type=Path)
    args = parser.parse_args()
    config = AppConfig.from_env()
    budget = LearningBudgetService(Database(config.DATABASE_URL), policy=LearningBudgetPolicy.load(args.policy),
                                    clock=lambda: int(time.time() * 1000))
    if args.mode == 'plan':
        if not (args.expires_at and args.approval_reference and args.approval_text) or any(
                value is not None for value in (args.plan, args.expected_plan_sha, args.sidecar_output)):
            parser.error('plan requires expires-at, approval-reference and current explicit approval-text only')
        result = plan_tail_renewal(budget=budget, expires_at=args.expires_at,
            approval_reference=args.approval_reference, approval_text=args.approval_text)
    else:
        if not (args.plan and args.expected_plan_sha and args.sidecar_output) or any(
                value is not None for value in (args.expires_at, args.approval_reference, args.approval_text)):
            parser.error('apply requires the reviewed plan, expected-plan-sha and sidecar-output only')
        document = json.loads(args.plan.read_bytes())
        result = apply_tail_renewal(budget=budget, plan=document['plan'], expected_plan_sha=args.expected_plan_sha)
    _archive(args.output.resolve(), result)
    if args.sidecar_output:
        _archive(args.sidecar_output.resolve(), result['sidecar'])
    print(json.dumps({'applied': result['applied'], 'planSha256': result['planSha256'],
        'authorizationId': result['sidecar']['authorizationId'], 'expiresAt': result['sidecar']['expiresAt'],
        'providerCalls': 0, 'output': str(args.output.resolve())}, ensure_ascii=False))


if __name__ == '__main__':
    main()
