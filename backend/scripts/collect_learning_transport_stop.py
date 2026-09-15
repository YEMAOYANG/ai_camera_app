"""Capture local process identity for an operator-reviewed transport drain.

probe is read-only. capture writes evidence; stop uses only the existing managed
stack stop command and verifies the relevant local processes actually exited.
It never calls a Provider or changes any billing row.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
PORTS = (3000, 3100, 3101, 8000)
AUDIT_SHA = 'cebd0b3f1d491452525e4707ff0afccd858955a38af858693b1e370d89d59267'
CHATGPT = Path('/Applications/ChatGPT.app/Contents/Resources')


def infrastructure_reason(process, processes):
    """Exact local tooling identities only; unknown interpreters stay blocking."""
    command = process['_command'].strip()
    executable = process.get('executablePath', '')
    if not executable or not Path(executable).is_file():
        return None
    basis = {'executablePath': executable}
    if executable in {'/bin/zsh', '/bin/bash'}:
        if re.fullmatch(re.escape(executable) + r'(?: -(?:i|l|il|li))?', command):
            return basis | {'classification': 'interactive_shell', 'basis': 'Exact system shell without command or script arguments'}
    if executable == str(CHATGPT / 'cua_node/bin/node_repl') and command == executable:
        return basis | {'classification': 'codex_cua_repl', 'basis': 'Bundled CUA REPL executable without application entry point'}
    if executable == str(CHATGPT / 'codex'):
        if command == executable + ' app-server --listen stdio://':
            return basis | {'classification': 'codex_app_server', 'basis': 'Exact bundled Codex stdio app-server command'}
        if (command.startswith(executable + ' sandbox ') and 'default_permissions="node_repl"' in command
                and str(CHATGPT / 'cua_node/bin/node') + ' --experimental-vm-modules ' in command
                and re.search(r'/\.tmp[^ /]+/(?:kernel|trusted-worker)\.js(?: |$)', command)):
            return basis | {'classification': 'codex_cua_sandbox', 'basis': 'Bundled Codex sandbox for its temporary CUA kernel or worker'}
    entries = re.findall(r'/[^\s"\']+\.(?:mjs|js)(?=\s|$)', command)
    for entry in entries:
        if not Path(entry).is_file():
            continue
        if executable == str(CHATGPT / 'cua_node/bin/node'):
            plugin_root = str(Path.home() / '.codex/plugins/cache/openai-bundled/unified-computer-use')
            if ((entry.startswith(plugin_root + '/') and entry.endswith('/scripts/launch.mjs'))
                    or entry == str(CHATGPT / 'artifact-template-picker/server.mjs')):
                return basis | {'classification': 'codex_bundled_plugin', 'entryPath': str(Path(entry).resolve()), 'basis': 'Bundled CUA Node plus verified installed plugin entry file'}
            parent = processes.get(process['ppid'], {})
            if (re.search(r'/\.tmp[^ /]+/(?:kernel|trusted-worker)\.js$', entry)
                    and parent.get('executablePath') == str(CHATGPT / 'codex')
                    and 'default_permissions="node_repl"' in parent.get('_command', '')):
                return basis | {'classification': 'codex_cua_worker', 'entryPath': str(Path(entry).resolve()), 'basis': 'Bundled CUA Node temporary kernel with verified Codex sandbox parent'}
        if executable.startswith('/Applications/Cursor.app/Contents/Frameworks/Cursor Helper (Plugin).app/'):
            cursor_extensions = str(Path.home() / '.cursor/extensions')
            if (entry.startswith(cursor_extensions + '/') and
                    re.search(r'/(?:bradlc\.vscode-tailwindcss-[^/]+/dist/tailwindServer|dbaeumer\.vscode-eslint-[^/]+/server/out/eslintServer|stylelint\.vscode-stylelint-[^/]+/dist/start-server)\.js$', entry)):
                return basis | {'classification': 'cursor_language_server', 'entryPath': str(Path(entry).resolve()), 'basis': 'Cursor helper executing verified Tailwind, ESLint or Stylelint extension server'}
    json_server = '/Applications/Cursor.app/Contents/Resources/app/extensions/json-language-features/server/dist/node/jsonServerMain'
    if (executable.startswith('/Applications/Cursor.app/Contents/Frameworks/Cursor Helper (Plugin).app/')
            and json_server + ' --node-ipc ' in command and Path(json_server + '.js').is_file()):
        return basis | {'classification': 'cursor_language_server', 'entryPath': json_server + '.js', 'basis': 'Cursor bundled JSON language server with node IPC and verified Node-resolved entry file'}
    if (process.get('cwd') == str(ROOT)
            and executable.startswith('/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Framework.framework/Versions/')
            and executable.endswith('/Helpers/chrome_crashpad_handler')
            and command.startswith(executable + ' --monitor-self-annotation=ptype=crashpad-handler ')
            and '--url=https://clients2.google.com/cr/report ' in command):
        return basis | {'classification': 'browser_crash_reporter', 'basis': 'Verified Chrome crash-report helper with fixed crash collection entry; no browser or application entry point'}
    if Path(executable).name == 'node':
        if command in {'npm exec @upstash/context7-mcp', 'npm exec @playwright/mcp@latest'}:
            return basis | {'classification': 'codex_mcp_launcher', 'basis': 'Exact Context7 or Playwright MCP npm launcher command'}
        match = re.fullmatch(r'node (' + re.escape(str(Path.home() / '.npm/_npx')) + r'/[a-f0-9]+/node_modules/\.bin/(context7-mcp|playwright-mcp))', command)
        if match and Path(match.group(1)).is_file():
            return basis | {'classification': 'codex_mcp_server', 'entryPath': str(Path(match.group(1)).resolve()), 'basis': 'Node executing verified cached Context7 or Playwright MCP entry'}
    if 'Python' in Path(executable).name or re.fullmatch(r'python(?:3(?:\.\d+)?)?', Path(executable).name):
        args = shlex.split(command)
        if len(args) >= 3 and args[1:3] == ['-m', 'http.server']:
            rest = args[3:]
            if rest and rest[0].isdigit():
                rest = rest[1:]
            valid = True
            while rest:
                if len(rest) < 2 or rest[0] not in {'--bind', '--directory'}:
                    valid = False; break
                rest = rest[2:]
            cwd = Path(process.get('cwd', '/'))
            if valid and not (cwd / 'http.py').exists() and not (cwd / 'http').exists():
                return basis | {'classification': 'python_static_http_server', 'basis': 'Python standard http.server module, only static bind/directory options, no local http module shadow'}
    return None


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def run(command, *, empty_ok=False):
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode != 0 and not (empty_ok and result.returncode == 1):
        raise RuntimeError('Local process inventory failed: ' + command[0])
    return result.stdout


def probe():
    processes = {}
    for line in run(['/bin/ps', '-axo', 'pid=,ppid=,lstart=,command=']).splitlines():
        parts = line.split(None, 7)
        if len(parts) != 8:
            continue
        pid, parent = int(parts[0]), int(parts[1])
        processes[pid] = {'pid': pid, 'ppid': parent, 'startIdentity': ' '.join(parts[2:7]),
                          'commandSha256': digest(parts[7].encode()), '_command': parts[7]}
    # Exclude only this read-only operator's own ancestor chain, never siblings
    # or descendants of the application servers.
    excluded = set()
    cursor = os.getpid()
    while cursor in processes and cursor not in excluded:
        excluded.add(cursor)
        cursor = processes[cursor]['ppid']
    pid = None
    descriptor = None
    for line in run(['/usr/sbin/lsof', '-nP', '-u', str(os.getuid()), '-a', '-d', 'cwd,txt', '-Fpfn'], empty_ok=True).splitlines():
        if line.startswith('p'):
            pid = int(line[1:])
        elif line.startswith('f'):
            descriptor = line[1:]
        elif line.startswith('n') and pid in processes:
            if descriptor == 'cwd':
                processes[pid]['cwd'] = line[1:]
            elif descriptor == 'txt' and 'executablePath' not in processes[pid] and os.access(line[1:], os.X_OK):
                processes[pid]['executablePath'] = line[1:]
    infrastructure = {}
    for pid, process in processes.items():
        if process.get('cwd') == str(ROOT) or process.get('cwd', '').startswith(str(ROOT) + '/'):
            reason = infrastructure_reason(process, processes)
            if reason:
                infrastructure[pid] = reason
    # Browser tools are infrastructure only when their ancestry is an identified
    # MCP browser tool. Chrome launched by Native remains a deployment process.
    while True:
        added = False
        for pid, process in processes.items():
            if pid in infrastructure:
                continue
            parent = infrastructure.get(process['ppid'], {})
            executable = process.get('executablePath', '')
            if (executable.startswith('/Applications/Google Chrome.app/Contents/') and Path(executable).is_file()
                    and (parent.get('classification') == 'codex_mcp_browser'
                         or (parent.get('classification') == 'codex_mcp_server'
                             and 'playwright' in parent.get('entryPath', '')
                             and '/Library/Caches/ms-playwright-mcp/' in process['_command']))):
                infrastructure[pid] = {'classification': 'codex_mcp_browser', 'executablePath': executable,
                    'basis': 'Verified Chrome executable descended from the identified Playwright MCP browser',
                    'parentPid': process['ppid']}
                added = True
        if not added:
            break
    selected = set()
    for pid, process in processes.items():
        cwd = process.get('cwd', '')
        if pid in excluded:
            continue
        if pid in infrastructure:
            continue
        if cwd == str(ROOT / 'backend') or cwd.startswith(str(ROOT / 'backend') + '/'):
            process['role'] = 'backend'
        elif cwd == str(ROOT / 'openmaic-runtime') or cwd.startswith(str(ROOT / 'openmaic-runtime') + '/'):
            process['role'] = 'native_or_gateway'
        elif cwd == str(ROOT / 'student-web') or cwd.startswith(str(ROOT / 'student-web') + '/'):
            process['role'] = 'student_web'
        elif cwd == str(ROOT):
            process['role'] = 'workspace_call_capable'
        else:
            continue
        selected.add(pid)
    ports = []
    for port in PORTS:
        listening = run(['/usr/sbin/lsof', '-nP', '-t', '-iTCP:' + str(port), '-sTCP:LISTEN'], empty_ok=True)
        owners = sorted({int(value) for value in listening.split()})
        ports.append({'port': port, 'pids': owners})
        selected.update(pid for pid in owners if pid in processes and pid not in excluded)
    while True:
        children = {pid for pid, process in processes.items()
                    if process['ppid'] in selected and pid not in excluded}
        if children <= selected:
            break
        selected |= children
    output = []
    for pid in sorted(selected):
        process = processes[pid]
        output.append({key: value for key, value in process.items() if key != '_command'}
                      | {'role': process.get('role', 'deployment_descendant')})
    excluded_output = []
    for pid, reason in sorted(infrastructure.items()):
        if pid in selected:
            continue
        process = processes[pid]
        excluded_output.append({key: process[key] for key in ('pid', 'ppid', 'startIdentity', 'commandSha256', 'cwd') if key in process} | reason)
    return {'processes': output, 'ports': ports, 'excludedInfrastructure': excluded_output}


def write_once(path, data):
    with open(path, 'x') as output:
        json.dump(data, output, ensure_ascii=False, sort_keys=True, indent=2)
        output.write('\n'); output.flush(); os.fsync(output.fileno())
    path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('probe', 'capture', 'stop'))
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--source-attribution', type=Path)
    args = parser.parse_args()
    if args.mode == 'probe':
        print(json.dumps(probe(), ensure_ascii=False)); return
    directory = args.directory.resolve()
    if args.mode == 'capture':
        directory.mkdir(mode=0o700, exist_ok=False)
        before = probe()
        if not before['processes']:
            raise RuntimeError('Expected running managed deployment before capture')
        evidence = {'schemaVersion': 'mira.learning.managed-transport-stop.v1',
                    'sourceAuditSha256': AUDIT_SHA, 'deploymentRoot': str(ROOT),
                    'capturedAt': int(time.time()*1000), 'before': before,
                    'sourceAttribution': json.loads(args.source_attribution.read_text())}
        write_once(directory / 'before.json', evidence)
        print(json.dumps({'captured': True, 'processCount': len(before['processes'])})); return
    evidence = json.loads((directory / 'before.json').read_text())
    current = probe()
    # A newly started service must first be captured in a new maintenance plan.
    identities = {(p['pid'], p['startIdentity'], p['commandSha256']) for p in evidence['before']['processes']}
    if any((p['pid'], p['startIdentity'], p['commandSha256']) not in identities for p in current['processes']):
        raise RuntimeError('Deployment process inventory changed after capture')
    command = ['/bin/bash', str(ROOT / 'openmaic-runtime/scripts/local-test-stack.sh'), 'stop']
    started = int(time.time()*1000)
    log_path = directory / 'managed-stop.log'
    with open(log_path, 'xb') as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    completed = int(time.time()*1000)
    after = probe()
    evidence.update(stoppedAt=completed, verifiedAt=int(time.time()*1000), after=after,
                    managedStop={'command': command, 'exitCode': result.returncode,
                                 'startedAt': started, 'completedAt': completed,
                                 'logPath': str(log_path), 'logSha256': digest(log_path.read_bytes())})
    target = directory / ('manifest.json' if result.returncode == 0 and not after['processes']
                         and all(not p['pids'] for p in after['ports']) else 'incomplete.json')
    write_once(target, evidence)
    if target.name != 'manifest.json':
        raise RuntimeError('Managed stop left local processes or ports; incomplete evidence retained')
    print(json.dumps({'stoppedAndVerified': True, 'manifestPath': str(target),
                      'manifestSha256': digest(target.read_bytes())}))


if __name__ == '__main__':
    main()
