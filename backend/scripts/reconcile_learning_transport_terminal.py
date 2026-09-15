"""Audited four-request local transport completion; no generation or Provider."""
import argparse
import json
from pathlib import Path
import sys
import time

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.config import AppConfig
from core.database import Database
from services.learning_transport_terminal_reconciliation import plan_reconciliation, apply_reconciliation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('plan', 'apply'))
    parser.add_argument('--source-audit', type=Path)
    parser.add_argument('--stop-evidence', type=Path)
    parser.add_argument('--approval-reference')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--expected-plan-sha')
    parser.add_argument('--confirm-managed-stack-stopped', action='store_true')
    args = parser.parse_args()
    if args.mode == 'plan':
        if not (args.source_audit and args.stop_evidence and args.approval_reference) or args.plan or args.expected_plan_sha:
            parser.error('plan requires source-audit, stop-evidence and approval-reference only')
    elif not (args.plan and args.expected_plan_sha and args.confirm_managed_stack_stopped) or args.source_audit or args.stop_evidence or args.approval_reference:
        parser.error('apply requires plan, expected-plan-sha and confirm-managed-stack-stopped only')
    # AppConfig reads the existing local configuration; no Flask/worker/schema startup.
    config = AppConfig.from_env()
    database = Database(config.DATABASE_URL)
    if args.mode == 'plan':
        result = plan_reconciliation(database=database, source_audit=args.source_audit,
                                    stop_evidence=args.stop_evidence, approval_reference=args.approval_reference)
    else:
        result = apply_reconciliation(database=database, plan_path=args.plan,
                                      expected_plan_sha=args.expected_plan_sha, now=int(time.time() * 1000))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
