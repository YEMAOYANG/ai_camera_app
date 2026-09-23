"""Plan or append the single approved slot-two local TTS termination audit."""
import argparse
import fcntl
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.config import AppConfig
from core.database import Database
from services.learning_audio_transport_terminal import prepare, apply


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("--expected-audit-sha")
    parser.add_argument("--confirm-workers-stopped", action="store_true")
    args = parser.parse_args()
    if args.mode == "apply" and not (args.expected_audit_sha and args.confirm_workers_stopped):
        parser.error("apply requires --expected-audit-sha and --confirm-workers-stopped")
    if args.mode == "plan" and (args.expected_audit_sha or args.confirm_workers_stopped):
        parser.error("plan takes no mutation options")
    database = Database(AppConfig.from_env().DATABASE_URL)
    with open("/tmp/mira-generate-one-formal-course.lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = prepare(database) if args.mode == "plan" else apply(database, args.expected_audit_sha)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
