#!/usr/bin/env python3
"""Run a disposable foreground command with one private temporary directory."""

import argparse
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time


def safe_name(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", value):
        raise argparse.ArgumentTypeError("use 1-48 lowercase letters, digits or hyphens; start with a letter or digit")
    return value


def group_running(process):
    try:
        os.killpg(process.pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def has_diagnostics(directory):
    for parent, directories, files in os.walk(directory, followlinks=False):
        for name in directories + files:
            path = Path(parent, name)
            if path.is_symlink() or (path.is_file() and path.stat().st_size):
                return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Usage: task_tmp.py --name check [--keep] -- command [args...]. "
        "stdout/stderr stay on the terminal. Put disposable files under MIRA_TASK_TMPDIR; "
        "TMPDIR points to the same directory. Success removes it; failure keeps nonempty diagnostics. "
        "--keep always retains it. Do not use for persistent services, databases, paid calls or recovery data. "
        "Background children in this command's process group prevent cleanup; detached services are unsupported.",
    )
    parser.add_argument("--name", type=safe_name, required=True)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command[:1] != ["--"] or len(args.command) < 2:
        parser.error("provide a command after --")
    command = args.command[1:]

    directory = Path(tempfile.mkdtemp(prefix="mira-task-" + args.name + "-"))
    directory.chmod(0o700)
    original = directory.stat()
    environment = dict(os.environ, MIRA_TASK_TMPDIR=str(directory), TMPDIR=str(directory) + os.sep)
    process = None
    interrupted = None
    deadline = None
    result = 1

    def forward(signum, _frame):
        nonlocal interrupted, deadline
        interrupted = interrupted or signum
        deadline = deadline or time.monotonic() + 3
        # A live, unreaped leader anchors the new process group to this command.
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass

    previous = {sig: signal.signal(sig, forward) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        process = subprocess.Popen(command, env=environment, start_new_session=True)
        if interrupted:
            forward(interrupted, None)
        while True:
            try:
                result = process.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if deadline is not None and time.monotonic() >= deadline:
                    # Never signal a group after reaping its leader.
                    if process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
        result = 128 + interrupted if interrupted else (128 - result if result < 0 else result)
    except OSError as error:
        print("task_tmp: " + str(error), file=sys.stderr)
        result = 127 if isinstance(error, FileNotFoundError) else 126
    finally:
        try:
            current = directory.lstat()
            changed = (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino)
            background = process is not None and group_running(process)
            retain = args.keep or changed or background or (result != 0 and has_diagnostics(directory))
            if retain:
                reason = "background children remain" if background else "explicit keep" if args.keep else "directory changed" if changed else "diagnostics"
                print("task_tmp: retained " + str(directory) + " (" + reason + ")", file=sys.stderr)
            else:
                shutil.rmtree(directory)
        except FileNotFoundError:
            pass
        except OSError as error:
            print("task_tmp: could not clean " + str(directory) + ": " + str(error), file=sys.stderr)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    return result


if __name__ == "__main__":
    sys.exit(main())
