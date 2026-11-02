"""Bounded background production for prepared immutable review requests.

The scheduler/operator prepares exact lesson-scoped input files first. This
worker calls only those frozen jobs; approval, media and student assignment are
separate. Unknown dispatches remain fenced across worker restarts.
"""
from __future__ import annotations

import argparse
import json
import signal
import threading

from scripts.prepare_learning_review_pack import main as batch


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--limit', type=int, default=5)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({'enabled': False, 'providerCalls': 0}))
        return
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while not stop.is_set():
        print(json.dumps(batch(['worker', '--execute', '--limit', str(args.limit)])), flush=True)
        if args.once:
            return
        stop.wait(15)


if __name__ == '__main__':
    main()
