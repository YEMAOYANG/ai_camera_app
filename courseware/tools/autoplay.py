"""Random-play check of the interactive pages: each must be finishable by tapping and dragging and must reset on 'play again'.

The bot (autoplay.mjs, Playwright and Chrome) opens every interactive scene as a standalone page and plays at random. It
finds what the generic audit cannot: soft locks (a level that never ends), errors that only show during play, a finish
overlay that does not reset. A page is ok when it finished at least once without script errors and 'play again' reset it;
a second finish is reported but not required, because random play needs many steps for the longer pages.
Real-time pages built on the shared game engine (courseware/kit/game.py) are first pressed and dragged at random to
surface errors, then finished twice by the engine's own autopilot over every level; their result says method
'game-autopilot' so the receipt never presents an autopilot finish as random play.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote

from courseware.tools.check import MEDIA_URL, body_hash, play_issues

CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
BOT = Path(__file__).with_name('autoplay.mjs')


def _playwright_dir():
    """The folder that holds node_modules/playwright-core (the student web app's dependency, often in the main checkout)."""
    root = Path(__file__).resolve().parents[2]
    candidates = [Path(os.environ['MIRA_PLAYWRIGHT_DIR'])] if os.environ.get('MIRA_PLAYWRIGHT_DIR') else []
    candidates.append(root / 'student-web')
    try:
        common = subprocess.run(['git', 'rev-parse', '--git-common-dir'], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        candidates.append((root / common).resolve().parent / 'student-web')
    except (OSError, subprocess.SubprocessError):
        pass
    for candidate in candidates:
        if (candidate / 'node_modules' / 'playwright-core').is_dir():
            return candidate
    raise RuntimeError('playwright-core not found; set MIRA_PLAYWRIGHT_DIR to a folder that holds node_modules/playwright-core')


def default_run(command, timeout):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout, result.stderr


def page_html(scene, media_dir):
    """The scene's page with its classroom media URLs pointing at the local media files."""
    def local(match):
        name = unquote(match.group().split('/media/', 1)[1])
        return (Path(media_dir) / name).resolve().as_uri()
    return MEDIA_URL.sub(local, scene.get('content', {}).get('html', ''))


def play_body(body, media_dir, *, run=default_run, work_dir=None, max_steps=400, seed=7):
    scenes = [(index, scene) for index, scene in enumerate(body.get('scenes', []), 1) if scene.get('type') == 'interactive']
    pages = []
    with tempfile.TemporaryDirectory(dir=work_dir) as temporary:
        for index, scene in scenes:
            (Path(temporary) / f'scene-{index:02d}.html').write_text(page_html(scene, media_dir), encoding='utf-8')
        node = os.environ.get('MIRA_NODE_BIN') or shutil.which('node') or 'node'
        command = [node, str(BOT), '--playwright', str(_playwright_dir()), '--chrome', os.environ.get('MIRA_CHROME_BIN', CHROME),
                   '--dir', temporary, '--max-steps', str(max_steps), '--seed', str(seed)]
        code, stdout, stderr = run(command, 120 + len(scenes) * max_steps)
        try:
            results = json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else []
        except ValueError:
            results = []
        if code or len(results) != len(scenes):
            raise RuntimeError(f'autoplay failed (exit {code}): {(stderr or stdout).strip()[-400:]}')
    for (index, _), result in zip(scenes, results):
        errors = sorted(set(result['errors']))
        stuck = result.get('stuck')
        page = {'scene': index, 'finished': bool(result['finishes']), 'stepsToFinish': result['finishes'][0] if result['finishes'] else None,
                'finishedAgain': len(result['finishes']) > 1, 'errors': errors, 'stuck': stuck,
                'ok': bool(result['finishes']) and not errors and not stuck, 'method': result.get('method', 'random')}
        if result.get('seconds'):
            page['secondsToFinish'] = result['seconds']
        pages.append(page)
    return {'schemaVersion': 'mira.courseware.autoplay-receipt.v1', 'bodySha256': body_hash(body), 'ok': all(p['ok'] for p in pages),
            'maxSteps': max_steps, 'seed': seed, 'pages': pages, 'tool': {'ranAt': datetime.now(timezone.utc).isoformat()}}


def issues(receipt):
    """Backward-compatible entry point for the shared blocking G6 interpretation."""
    return play_issues(receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--body', required=True)
    parser.add_argument('--media-dir', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--max-steps', type=int, default=400)
    parser.add_argument('--seed', type=int, default=7)
    args = parser.parse_args(argv)
    try:
        body = json.loads(Path(args.body).read_text(encoding='utf-8'))
        receipt = play_body(body, args.media_dir, max_steps=args.max_steps, seed=args.seed)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'autoplay failed: {exc}', file=sys.stderr)
        return 2
    Path(args.out).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for page in receipt['pages']:
        print('scene %s: %s' % (page['scene'], 'ok' if page['ok'] else 'FAILED ' + (page['stuck'] or '; '.join(page['errors']) or 'never finished')))
    return int(not receipt['ok'])


if __name__ == '__main__':
    raise SystemExit(main())
