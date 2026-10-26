#!/usr/bin/env python
"""Verify pulled night products against their run manifests (plan S15a "Verify").

Usage:
    conda run -n pypeit14b python nautilus/verify_nights.py NIGHT [NIGHT ...]
        [--instrument mosfire] [--digest sha256:...] [--pin SHA]

Run after ``s3_sync.py pull <instrument>/<night> --include 'sens/*' 'harvest/*'
run_manifest.json 'redux/Calibrations/WaveCalib_*'``. For every night, from
``$KECK_ETCS_DATA/<instrument>/<night>``:

- ``run_manifest.json``: ``status`` success, gates passed, and (when given)
  ``image_digest`` and ``pypeit_git_sha`` equal to ``--digest`` / ``--pin``
  (a night may come from either of several images: give ``--digest``
  more than once);
- every local ``sens/*.fits`` and ``redux/Calibrations/WaveCalib_*`` file
  matches its sha256 in ``product_sha256`` (a file on the bucket left by an
  earlier, failed run of the same night with the same size is not
  re-pushed by the success path, so a mismatch means a stale product);
- ``sens/*.fits`` files on disk that the manifest does not list (leftovers of
  earlier runs) are reported;
- a harvest row (``harvest/<STD>_<night>_row.ecsv``) exists;
- ``pod_usage`` (wall-clock, scratch, peak memory) is printed.

Read-only. Exit 1 if any night fails a check.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from keck_etcs import paths


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def check(night_dir, digests, pin):
    problems, notes = [], []
    mp = night_dir / 'run_manifest.json'
    if not mp.exists():
        return [f'no {mp.name}'], notes, None
    m = json.loads(mp.read_text())
    if m.get('status') != 'success':
        problems.append(f"status {m.get('status')}")
    g = m.get('gates') or {}
    if not g.get('pass'):
        problems.append(f"gates {g.get('failed')}")
    if digests and m.get('image_digest') not in digests:
        problems.append(f"image_digest {m.get('image_digest')}")
    if pin and m.get('pypeit_git_sha') != pin:
        problems.append(f"pypeit_git_sha {m.get('pypeit_git_sha')} != pin {pin}")
    prod = m.get('product_sha256') or {}
    local = sorted(night_dir.glob('sens/*.fits')) + sorted(night_dir.glob('redux/Calibrations/WaveCalib_*'))
    n_ok = 0
    for f in local:
        rel = str(f.relative_to(night_dir))
        if rel not in prod:
            if rel.startswith('sens/'):
                notes.append(f'not in manifest (leftover of an earlier run?): {rel}')
            continue
        if sha256(f) != prod[rel]:
            problems.append(f'sha256 mismatch (stale?): {rel}')
        else:
            n_ok += 1
    missing = [k for k in prod if k.startswith('sens/') and not (night_dir / k).exists()]
    if missing:
        problems.append(f'listed but not pulled: {missing}')
    std = (m.get('standard') or {}).get('name') or next(
        (f['target'] for f in m['frames'] if 'standard' in f['frametype']), '')
    rows = sorted(night_dir.glob('harvest/*_row.ecsv'))
    if not rows:
        problems.append('no harvest row')
    notes.append(f'{n_ok} products match their sha256; harvest rows {[r.name for r in rows]}')
    return problems, notes, m


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('nights', nargs='+')
    ap.add_argument('--instrument', default='mosfire')
    ap.add_argument('--digest', action='append', default=[], help='accepted image digest(s)')
    ap.add_argument('--pin', help='expected pypeit_git_sha')
    a = ap.parse_args(argv)
    bad = 0
    for n in a.nights:
        nd = paths.night_dir(a.instrument, n)
        problems, notes, m = check(nd, set(a.digest), a.pin)
        u = (m or {}).get('pod_usage') or {}
        img = (m or {}).get('image')
        print(f"{n}: {'OK' if not problems else 'FAIL'} | image {img} {(m or {}).get('image_digest')} | "
              f"PypeIt {(m or {}).get('pypeit_git_sha')} | job {(m or {}).get('job_name')} | "
              f"wall {u.get('wall_clock_s')} s, scratch {u.get('scratch_bytes')}, memory_peak {u.get('memory_peak_bytes')}")
        for p in problems:
            print(f'   PROBLEM {p}')
        for x in notes:
            print(f'   {x}')
        bad += bool(problems)
    print('ALL OK' if not bad else f'{bad} night(s) with problems')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
