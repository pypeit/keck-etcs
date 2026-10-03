#!/usr/bin/env python
"""Per-night status table from the ``run_manifest.json`` objects on the bucket (store-only).

Usage:
    python nautilus/status_table.py [--instrument mosfire] [--out FILE.ecsv]

Lists ``s3://$KECK_ETCS_BUCKET/<instrument>/<YYYYMMDD>/run_manifest.json`` (one
per reduced night; ``reference/`` copies and other depths are ignored), reads
each object, and writes one row per night:
``night, status, image, image_digest, pypeit_version, pypeit_git_sha,
pypeit_pin, pin_check_pass, keck_etcs_git_sha, job_name, finished, n_objects,
gates_pass, gates_failed, error``.

Store-only: nothing is reduced or written to the bucket. The table goes to
``$KECK_ETCS_DATA/<instrument>/status_table.ecsv`` by default.
Credentials as for ``scripts/nautilus/s3_sync.py``.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from astropy.table import Table

from keck_etcs import paths

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts' / 'nautilus'))
import s3_sync  # noqa: E402


def main(instrument='mosfire', out=None):
    client = s3_sync.make_client()
    keys = sorted(k for k in s3_sync.remote_sizes(client, paths.BUCKET, instrument)
                  if re.fullmatch(rf'{instrument}/\d{{8}}/run_manifest\.json', k))
    rows = []
    for key in keys:
        m = json.loads(client.get_object(Bucket=paths.BUCKET, Key=key)['Body'].read())
        g = m.get('gates') or {}
        rows.append({
            'night': m.get('night', key.split('/')[1]), 'status': m.get('status') or '',
            'image': m.get('image') or '', 'image_digest': m.get('image_digest') or '',
            'pypeit_version': m.get('pypeit_version') or '',
            'pypeit_git_sha': m.get('pypeit_git_sha') or '', 'pypeit_pin': m.get('pypeit_pin') or '',
            'pin_check_pass': bool((m.get('pin_check') or {}).get('pass')),
            'keck_etcs_git_sha': m.get('keck_etcs_git_sha') or '', 'job_name': m.get('job_name') or '',
            'finished': m.get('finished') or '', 'n_objects': len(m.get('objects') or []),
            'gates_pass': bool(g.get('pass')), 'gates_failed': ','.join(g.get('failed') or []),
            'error': (m.get('error') or '')[:200]})
    if not rows:
        print(f'no run_manifest.json under s3://{paths.BUCKET}/{instrument}/')
        return 1
    tbl = Table(rows=rows)
    out = Path(out) if out else paths.data_root() / instrument / 'status_table.ecsv'
    out.parent.mkdir(parents=True, exist_ok=True)
    tbl.write(out, format='ascii.ecsv', overwrite=True)
    tbl['night', 'status', 'image', 'pypeit_pin', 'keck_etcs_git_sha', 'gates_pass',
        'gates_failed'].pprint(max_lines=-1, max_width=-1)
    print(f'{len(tbl)} night(s) -> {out}')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--instrument', default='mosfire')
    p.add_argument('--out', help='Output ECSV')
    sys.exit(main(**vars(p.parse_args())))
