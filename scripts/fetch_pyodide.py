#!/usr/bin/env python
"""Fetch the Pyodide files the interactive ETC page needs, for self-hosting (plan S21, Q&A S21-2 (b)).

Usage:
    python scripts/fetch_pyodide.py [--out docs/_generated/static/pyodide] [--version 314.0.7]
    python scripts/fetch_pyodide.py --record      # (re)write docs/pyodide_core.sha256 after a version bump

``docs/conf.py`` calls :func:`fetch` at every documentation build, so the readers' browsers load Pyodide
from the documentation site itself and make no third-party request. The build machine downloads, once
per build, from the pinned release on jsDelivr (``https://cdn.jsdelivr.net/pyodide/v<version>/full/``):

- the core files ``CORE`` (the loader, the WebAssembly runtime, the standard library and
  ``pyodide-lock.json``), each checked against ``docs/pyodide_core.sha256`` (committed; written by
  ``--record``, which is the only step that trusts the CDN);
- the wheels of ``PACKAGES`` and their dependency closure from ``pyodide-lock.json``, each checked
  against the sha256 recorded in that (already verified) lock file.

The list was measured in a browser (``scripts/pyodide_check.py --log-requests``): these are all the
files ``loadPyodide`` and ``loadPackage`` request for ``keck_etcs.etc.compute``. Files already present
with the right hash are not downloaded again. Standard library only. Exit 1 on a hash mismatch.
"""
import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERSION = '314.0.7'
CORE = ['pyodide.js', 'pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']
PACKAGES = ['numpy', 'scipy', 'astropy', 'pyyaml', 'jsonschema', 'micropip']
MANIFEST = REPO / 'docs' / 'pyodide_core.sha256'
DEFAULT_OUT = REPO / 'docs' / '_generated' / 'static' / 'pyodide'


def _url(version, name):
    return f'https://cdn.jsdelivr.net/pyodide/v{version}/full/{name}'


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _get(url, dest):
    tmp = dest.with_suffix(dest.suffix + '.part')
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, 'wb') as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)


def _norm(name):
    return name.lower().replace('_', '-')


def closure(lock, names):
    """Package names (lock keys) needed by ``names``, dependencies included."""
    pkgs = {_norm(k): k for k in lock['packages']}
    seen, stack = set(), [_norm(n) for n in names]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack += [_norm(d) for d in lock['packages'][pkgs[n]]['depends']]
    return sorted(pkgs[n] for n in seen)


def read_manifest(path=MANIFEST):
    out = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            sha, name = line.split()
            out[name] = sha
    return out


def fetch(out=DEFAULT_OUT, version=VERSION, log=print):
    """Download (or reuse) the files into ``out/v<version>/``; return that directory."""
    dest = Path(out) / f'v{version}'
    dest.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest()
    if f'Pyodide {version} ' not in MANIFEST.read_text().splitlines()[0]:
        raise RuntimeError(f'{MANIFEST.name} is not for Pyodide {version}; run scripts/fetch_pyodide.py --record')
    want = {name: manifest.get(name) for name in CORE}
    missing = [n for n, s in want.items() if s is None]
    if missing:
        raise RuntimeError(f'{MANIFEST.name} has no sha256 for {missing}; run scripts/fetch_pyodide.py --record')
    n_down = total = 0
    for name, sha in want.items():
        f = dest / name
        if not (f.exists() and _sha256(f) == sha):
            _get(_url(version, name), f)
            n_down += 1
            if _sha256(f) != sha:
                f.unlink()
                raise RuntimeError(f'sha256 mismatch for {name} (Pyodide {version})')
        total += f.stat().st_size
    lock = json.loads((dest / 'pyodide-lock.json').read_text())
    if lock['info'].get('version', version) != version:
        raise RuntimeError(f"pyodide-lock.json is for {lock['info'].get('version')}, not {version}")
    for key in closure(lock, PACKAGES):
        entry = lock['packages'][key]
        f = dest / entry['file_name']
        if not (f.exists() and _sha256(f) == entry['sha256']):
            _get(_url(version, entry['file_name']), f)
            n_down += 1
            if _sha256(f) != entry['sha256']:
                f.unlink()
                raise RuntimeError(f"sha256 mismatch for {entry['file_name']}")
        total += f.stat().st_size
    log(f'[fetch_pyodide] Pyodide {version}: {len(CORE)} core files + {len(closure(lock, PACKAGES))} packages, '
        f'{total / 1e6:.1f} MB in {dest} ({n_down} downloaded, all sha256 verified)')
    return dest


def record(version=VERSION):
    """Download the core files from the CDN and write their sha256 to ``docs/pyodide_core.sha256``."""
    lines = [f'# sha256 of the Pyodide {version} core files (scripts/fetch_pyodide.py --record; '
             f'source {_url(version, "")})']
    tmp = REPO / 'docs' / '_generated' / 'pyodide_record'
    tmp.mkdir(parents=True, exist_ok=True)
    for name in CORE:
        _get(_url(version, name), tmp / name)
        lines.append(f'{_sha256(tmp / name)}  {name}')
    MANIFEST.write_text('\n'.join(lines) + '\n')
    print(f'wrote {MANIFEST}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--out', default=str(DEFAULT_OUT))
    p.add_argument('--version', default=VERSION)
    p.add_argument('--record', action='store_true')
    a = p.parse_args()
    if a.record:
        record(a.version)
        return 0
    fetch(a.out, a.version)
    return 0


if __name__ == '__main__':
    sys.exit(main())
