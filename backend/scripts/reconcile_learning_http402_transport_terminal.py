"""Prepare/apply the exact EN2 local HTTP402 terminal proof; no Provider calls."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import AppConfig
from core.database import Database
from services.learning_http402_transport_terminal import prepare, apply

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'apply'))
    p.add_argument('--expected-audit-sha')
    a = p.parse_args()
    if (a.mode == 'apply') != bool(a.expected_audit_sha):
        p.error('apply requires --expected-audit-sha; prepare does not take one')
    database = Database(AppConfig.from_env().DATABASE_URL)
    result = prepare(database) if a.mode == 'prepare' else apply(database, a.expected_audit_sha)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
