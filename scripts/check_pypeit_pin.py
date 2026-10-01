#!/usr/bin/env python
"""Check that the local PypeIt is MOSFIRE-equivalent to the image pin (design D35).

Usage:
    conda run -n pypeit14b python scripts/check_pypeit_pin.py [--checkout DIR]
        [--pin SHA] [--allowlist FILE] [--json FILE] [--image TAG]

Prints ``pypeit.__version__``, ``pypeit.__file__``, the checkout's HEAD SHA
and branch, the pin (``nautilus/pypeit_pin.txt``), and the files that differ
from the pin: ``git diff --name-only <pin> HEAD`` plus uncommitted changes
(``git status --porcelain``, untracked files included). Then:

1. PASS/FAIL: ``git merge-base --is-ancestor <pin> HEAD``;
2. PASS/FAIL: every listed file matches ``nautilus/pypeit_pin_allowlist.txt``
   (offending files are named).

With ``--image TAG`` it also runs the container image and requires its
``KECK_ETCS_GIT_SHAS`` (JSON) ``pypeit`` entry to equal the pin exactly (the
local checkout's SHA may differ by design and is only reported).

Inside the image (PypeIt pip-installed, no git work tree, and
``KECK_ETCS_GIT_SHAS`` set) the check runs in *image mode*: it passes if and
only if ``KECK_ETCS_GIT_SHAS.pypeit`` equals the pin, with an empty file list
(design 4.8.5).

Writes a JSON result (``pypeit_git_sha``, ``pypeit_pin``, ``pin_check:
{pass, files, ...}``) for the reduction driver to copy into
``run_manifest.json``; the default location is
``$KECK_ETCS_DATA/pypeit_pin_check.json``. Exits 0 on PASS, 1 on FAIL,
2 on a usage or git error. Only read-only git commands are run.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PIN_FILE = REPO / 'nautilus' / 'pypeit_pin.txt'
ALLOWLIST = REPO / 'nautilus' / 'pypeit_pin_allowlist.txt'


def git(checkout, *args, check=True):
    res = subprocess.run(['git', '-C', str(checkout), *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)} failed: {res.stderr.strip()}')
    return res


def glob_to_regex(pattern):
    """Translate a glob with ``*``, ``?`` and ``**`` into an anchored regex."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith('**/', i):
            out.append('(?:.*/)?')
            i += 3
        elif pattern.startswith('**', i):
            out.append('.*')
            i += 2
        elif pattern[i] == '*':
            out.append('[^/]*')
            i += 1
        elif pattern[i] == '?':
            out.append('[^/]')
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile('^' + ''.join(out) + '$')


def read_allowlist(path):
    rules = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        negate = line.startswith('!')
        pat = line[1:] if negate else line
        rules.append((not negate, pat, glob_to_regex(pat)))
    return rules


def allowed(path, rules):
    """Last matching rule wins; a path no rule matches is not allowed."""
    verdict = False
    for allow, _pat, rx in rules:
        if rx.match(path):
            verdict = allow
    return verdict


def changed_files(checkout, pin):
    diff = git(checkout, 'diff', '--name-only', pin, 'HEAD').stdout.split()
    status = []
    for line in git(checkout, 'status', '--porcelain').stdout.splitlines():
        path = line[3:]
        if ' -> ' in path:          # rename: count both sides
            status.extend(path.split(' -> '))
        else:
            status.append(path)
    status = [p.strip('"') for p in status]
    return sorted(set(diff)), sorted(set(status))


def image_pypeit_sha(tag):
    cmd = ['docker', 'run', '--rm', tag, 'python', '-c',
           "import os; print(os.environ.get('KECK_ETCS_GIT_SHAS', ''))"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f'docker run {tag} failed: {res.stderr.strip()}')
    raw = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else ''
    if not raw:
        raise RuntimeError(f'{tag}: KECK_ETCS_GIT_SHAS is not set in the image')
    return json.loads(raw).get('pypeit'), raw


def write_result(result, json_path):
    out = Path(json_path) if json_path else None
    if out is None:
        from keck_etcs import paths
        out = paths.data_root() / 'pypeit_pin_check.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(f'\nWrote {out}')


def image_mode(pypeit, pin, args):
    """Pin check inside the container: the baked PypeIt SHA must equal the pin."""
    raw = os.environ['KECK_ETCS_GIT_SHAS']
    sha = json.loads(raw).get('pypeit')
    passed = sha is not None and (sha == pin or (len(pin) < 40 and sha.startswith(pin)))
    print(f'pypeit.__version__ : {pypeit.__version__}')
    print(f'pypeit.__file__    : {pypeit.__file__}')
    print(f'mode               : image (no git work tree; KECK_ETCS_GIT_SHAS={raw})')
    print(f'pin                : {pin}')
    print(f'(1) KECK_ETCS_GIT_SHAS.pypeit == pin : {"PASS" if passed else "FAIL"}')
    result = {
        'pypeit_git_sha': sha, 'pypeit_pin': pin, 'pypeit_version': pypeit.__version__,
        'pypeit_branch': None,
        'checked': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'pin_check': {'pass': bool(passed), 'files': [], 'ancestor': None, 'offending': [],
                      'mode': 'image'},
    }
    write_result(result, args.json)
    print(f'\nPIN CHECK: {"PASS" if passed else "FAIL"}')
    return 0 if passed else 1


def main(args):
    import pypeit

    checkout = Path(args.checkout) if args.checkout else Path(pypeit.__file__).resolve().parents[1]
    pin = (args.pin or PIN_FILE.read_text().split()[0]).strip()
    in_git = git(checkout, 'rev-parse', '--git-dir', check=False).returncode == 0
    if not in_git and not args.checkout and os.environ.get('KECK_ETCS_GIT_SHAS'):
        return image_mode(pypeit, pin, args)
    try:
        head = git(checkout, 'rev-parse', 'HEAD').stdout.strip()
        branch = git(checkout, 'branch', '--show-current').stdout.strip() or '(detached)'
        pin_full = git(checkout, 'rev-parse', '--verify', f'{pin}^{{commit}}').stdout.strip()
    except RuntimeError as exc:
        print(f'ERROR: {exc}')
        return 2

    print(f'pypeit.__version__ : {pypeit.__version__}')
    print(f'pypeit.__file__    : {pypeit.__file__}')
    print(f'checkout           : {checkout}')
    print(f'HEAD               : {head} ({branch})')
    print(f'pin                : {pin_full}' + (' (from --pin)' if args.pin else f' ({PIN_FILE.name})'))
    print(f'allow-list         : {args.allowlist}')

    ancestor = git(checkout, 'merge-base', '--is-ancestor', pin_full, 'HEAD', check=False).returncode == 0
    diff, status = changed_files(checkout, pin_full)
    files = sorted(set(diff) | set(status))
    print(f'\ngit diff --name-only <pin> HEAD: {len(diff)} file(s)')
    for f in diff:
        print(f'  {f}')
    print(f'git status --porcelain: {len(status)} file(s)')
    for f in status:
        print(f'  {f}')

    rules = read_allowlist(args.allowlist)
    offending = [f for f in files if not allowed(f, rules)]

    print(f'\n(1) pin is an ancestor of HEAD      : {"PASS" if ancestor else "FAIL"}')
    print(f'(2) all changed files allow-listed  : {"PASS" if not offending else "FAIL"}')
    for f in offending:
        print(f'      not allowed: {f}')

    image = None
    image_ok = True
    if args.image:
        try:
            image_sha, raw = image_pypeit_sha(args.image)
            image_ok = image_sha == pin_full
            image = {'tag': args.image, 'KECK_ETCS_GIT_SHAS': raw, 'pypeit': image_sha,
                     'pass': image_ok}
        except (RuntimeError, json.JSONDecodeError) as exc:
            image_ok = False
            image = {'tag': args.image, 'error': str(exc), 'pass': False}
        print(f'(3) image {args.image} PypeIt == pin : {"PASS" if image_ok else "FAIL"}'
              + (f"  ({image.get('pypeit') or image.get('error')})"))

    passed = ancestor and not offending and image_ok
    result = {
        'pypeit_git_sha': head,
        'pypeit_pin': pin_full,
        'pypeit_version': pypeit.__version__,
        'pypeit_branch': branch,
        'checked': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'pin_check': {
            'pass': passed,
            'files': files,
            'ancestor': ancestor,
            'offending': offending,
            'allowlist': str(Path(args.allowlist).resolve()),
        },
    }
    if image is not None:
        result['pin_check']['image'] = image

    write_result(result, args.json)
    print(f'\nPIN CHECK: {"PASS" if passed else "FAIL"}')
    return 0 if passed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--checkout', help='PypeIt checkout (default: the one pypeit is imported from)')
    parser.add_argument('--pin', help=f'Override the pin SHA (default: {PIN_FILE.name})')
    parser.add_argument('--allowlist', default=str(ALLOWLIST), help='Allow-list file')
    parser.add_argument('--json', help='Output JSON (default: $KECK_ETCS_DATA/pypeit_pin_check.json)')
    parser.add_argument('--image', metavar='TAG', help='Also require the image PypeIt SHA to equal the pin')
    sys.exit(main(parser.parse_args()))
