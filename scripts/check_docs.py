#!/usr/bin/env python
"""Check that the documentation agrees with the code, the schemas and the shipped data (plan S18).

Usage:
    conda run -n pypeit14b python scripts/check_docs.py

1. **WMKO note covers the schemas:** every leaf field of
   ``keck_etcs/schema/etc_input.json`` and ``etc_output.json`` (dotted
   paths, e.g. ``source.mag``, ``summary.snr_line``) appears in backticks in
   ``docs/wmko_api_note.md``; fields the note names that the schemas do not
   have are reported too.
2. **README examples run as written:** the ``python`` block of ``README.md``
   is executed. Each ``print`` line's trailing comment (up to `` (``) must
   appear in the corresponding output line. The first line of the CLI
   ``--summary`` block must equal what ``bin/keck_etc examples/J_point.json
   --summary`` prints.
3. **One calibration version everywhere:**
   - the ``calib_version`` of every ``index.yaml`` entry;
   - the latest release heading of ``CHANGES.md``;
   - ``meta.calib_version`` of ``compute`` in every era;
   - the tag named in ``README.md``, ``nautilus/README.md`` and the WMKO note.
4. **Images and pins agree:**
   - every (tag, digest, PypeIt pin) of the latest release in ``CHANGES.md``
     is a row of the image table in ``nautilus/README.md``;
   - the images and pins in the era files' ``meta`` are listed in
     ``CHANGES.md``;
   - the Job manifests use the README's current image;
   - ``nautilus/pypeit_pin.txt`` is that image's pin;
   - ``keck_etcs.__version__`` is that tag (or the next one, before its
     build).
5. **No secret in a document:** git-tracked and new text files under the
   repo (``*.md``, ``*.py``, ``*.yaml``, ``*.yml``, ``*.txt``, ``*.json``,
   ``*.csv``, ``*.ecsv``, ``*.patch``, ``*.sh``, the Dockerfile, ``bin/*``)
   are scanned for:
   - AWS access key IDs (``AKIA``/``ASIA`` + 16);
   - 40-character AWS secret-key-like strings (mixed case, digits and ``/``
     or ``+``);
   - GitLab tokens (``glpat-``, ``gldt-``);
   - private-key blocks;
   - ``secret``/``password``/``token`` assignments with a literal value.

Read-only. Exit 1 if any check fails.
"""
import contextlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
DOCS_SCAN = ('.md', '.py', '.yaml', '.yml', '.txt', '.json', '.csv', '.patch', '.sh', 'Dockerfile', '.ecsv')


def leaf_paths(schema, prefix=''):
    """Dotted paths of the leaf properties of a JSON schema object."""
    out = []
    for key, prop in schema.get('properties', {}).items():
        path = f'{prefix}{key}'
        if prop.get('properties'):
            out += leaf_paths(prop, path + '.')
        else:
            out.append(path)
    return out


def check_wmko_note():
    note = (REPO / 'docs' / 'wmko_api_note.md').read_text()
    ticks = set(re.findall(r'`([^`]+)`', note))
    bad = []
    for name in ('etc_input', 'etc_output'):
        sch = json.loads((REPO / 'keck_etcs' / 'schema' / f'{name}.json').read_text())
        paths = leaf_paths(sch)
        missing = [p for p in paths if p not in ticks]
        print(f'   {name}.json: {len(paths)} leaf fields, {len(paths) - len(missing)} in the note'
              + (f'; MISSING {missing}' if missing else ''))
        bad += [f'{name}: {p}' for p in missing]
    all_paths = set(leaf_paths(json.loads((REPO / 'keck_etcs/schema/etc_input.json').read_text()))) | \
        set(leaf_paths(json.loads((REPO / 'keck_etcs/schema/etc_output.json').read_text())))
    dotted = {t for t in ticks if re.fullmatch(r'(meta|summary|saturation|source|spectrum|readout|aperture|throughput)'
                                                 r'\.[a-z_.A-Z]+', t)}
    extra = sorted(dotted - all_paths)
    if extra:
        print(f'   named in the note but not in the schemas: {extra}')
        bad += [f'not in schema: {e}' for e in extra]
    return bad


def check_readme_examples():
    text = (REPO / 'README.md').read_text()
    bad = []
    block = re.search(r'```python\n(.*?)```', text, re.S).group(1)
    expected = []
    for line in block.splitlines():
        if line.lstrip().startswith('print('):
            m = re.search(r'#\s*(.+)$', line)
            expected.append(m.group(1).split(' (')[0].strip() if m else None)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(block, 'README.md', 'exec'), {})
    got = buf.getvalue().splitlines()
    for i, exp in enumerate(expected):
        line = got[i] if i < len(got) else ''
        ok = exp is None or exp in line
        print(f'   python print {i + 1}: {line!r}' + ('' if exp is None else f" (expects {exp!r}: {'OK' if ok else 'FAIL'})"))
        if not ok:
            bad.append(f'README python print {i + 1}')
    summ = re.search(r'`--summary` prints:\n\n```\n(.*?)\n', text).group(1)
    cli = subprocess.run([sys.executable, str(REPO / 'bin' / 'keck_etc'), str(REPO / 'examples' / 'J_point.json'),
                          '--summary'], capture_output=True, text=True, cwd=REPO)
    first = cli.stdout.splitlines()[0] if cli.stdout else cli.stderr
    ok = cli.returncode == 0 and first == summ
    print(f"   CLI --summary first line: {first!r} -> {'OK' if ok else 'FAIL (README: ' + repr(summ) + ')'}")
    if not ok:
        bad.append('README CLI')
    second = re.search(r'`--summary` prints:\n\n```\n.*?\n(.*?)\n', text).group(1)
    if cli.returncode == 0 and cli.stdout.splitlines()[1] != second:
        print(f'   CLI --summary second line differs: {cli.stdout.splitlines()[1]!r} vs README {second!r}')
        bad.append('README CLI line 2')
    return bad


def latest_release(changes):
    m = re.search(r'^### (mosfire-J-\d{4}\.\d{2})(?!-dev)\b.*$', changes, re.M)
    return m.group(1), m.start()


def release_triplets(changes, start):
    end = changes.find('\n### ', start + 4)
    sec = changes[start:end if end > 0 else None]
    return re.findall(r'`keck-etcs:([0-9.]+)` \| (sha256:[0-9a-f]{64}) \| ([0-9a-f]{40})', sec)


def readme_images():
    rows = {}
    current = None
    for line in (REPO / 'nautilus' / 'README.md').read_text().splitlines():
        m = re.match(r'\| (\d+\.\d+\.\d+) \| `([0-9a-f]{40})`[^|]*\| `([0-9a-f]+)` \| `(sha256:[0-9a-f]{64})` \|(.*)\|$', line)
        if m:
            rows[m.group(1)] = (m.group(4), m.group(2))
            if '**Current**' in m.group(5):
                current = m.group(1)
    return rows, current


def check_versions_and_images():
    import keck_etcs
    from keck_etcs import etc
    from keck_etcs.instruments.base import DATA_DIR
    from keck_etcs.instruments.mosfire import MOSFIRE
    from astropy.table import Table
    bad = []
    changes = (REPO / 'CHANGES.md').read_text()
    tag, start = latest_release(changes)
    index = yaml.safe_load((REPO / 'keck_etcs' / 'data' / 'index.yaml').read_text())['files']
    idx_versions = sorted({v['calib_version'] for v in index.values()})
    ok = idx_versions == [tag]
    print(f"   index.yaml calib_version {idx_versions}, CHANGES.md latest release {tag} -> {'OK' if ok else 'FAIL'}")
    if not ok:
        bad.append('index.yaml vs CHANGES')
    for era in MOSFIRE.eras:
        d = era.start if len(era.start) == 10 else era.start[:7] + '-15'
        m = etc.compute({'throughput': {'date': d}})['meta']
        ok = m['calib_version'] == tag and m['era'] == era.name
        print(f"   compute era {era.name}: calib_version {m['calib_version']} -> {'OK' if ok else 'FAIL'}")
        if not ok:
            bad.append(f'compute {era.name}')
    for doc in ('README.md', 'nautilus/README.md', 'docs/wmko_api_note.md'):
        ok = tag in (REPO / doc).read_text()
        print(f"   {doc} names {tag}: {'OK' if ok else 'FAIL'}")
        if not ok:
            bad.append(f'{doc} tag')

    rows, current = readme_images()
    triplets = release_triplets(changes, start)
    for t, dig, pin in triplets:
        ok = rows.get(t) == (dig, pin)
        print(f"   CHANGES {tag}: keck-etcs:{t} {dig[:19]}... pin {pin[:7]} in nautilus/README -> {'OK' if ok else 'FAIL'}")
        if not ok:
            bad.append(f'image {t}')
    listed = {(f'keck-etcs:{t}', d, p) for t, d, p in triplets}
    for era in MOSFIRE.eras:
        meta = Table.read(DATA_DIR / MOSFIRE.throughput_file(era), format='ascii.ecsv').meta
        imgs = {i.split('/')[-1] for i in meta['images']}
        miss = sorted(imgs - {x[0] for x in listed}) + sorted(set(meta['image_digests']) - {x[1] for x in listed}) \
            + sorted(set(meta['pypeit_git_shas']) - {x[2] for x in listed})
        print(f"   era {era.name}: images {sorted(imgs)} -> {'OK' if not miss else 'NOT IN CHANGES ' + str(miss)}")
        if miss:
            bad.append(f'era meta {era.name}')

    pin = (REPO / 'nautilus' / 'pypeit_pin.txt').read_text().strip()
    ok = current is not None and rows[current][1] == pin
    print(f"   nautilus/README current image {current}, pin {rows.get(current, ('', ''))[1][:7]}; "
          f"pypeit_pin.txt {pin[:7]} -> {'OK' if ok else 'FAIL'}")
    if not ok:
        bad.append('pin')
    for y in ('night_job.yaml', 'validate_job.yaml', 'koa_download_job.yaml'):
        txt = (REPO / 'nautilus' / y).read_text()
        tags = set(re.findall(r'image: \S+/keck-etcs:(\S+)', txt))
        digs = set(re.findall(r'sha256:[0-9a-f]{64}', txt))
        ok = tags == {current} and digs <= {rows[current][0]}
        print(f"   {y}: image {sorted(tags)} -> {'OK' if ok else 'FAIL'}")
        if not ok:
            bad.append(y)
    v = keck_etcs.__version__
    ok = v == current or tuple(map(int, v.split('.'))) > tuple(map(int, current.split('.')))
    print(f"   keck_etcs.__version__ {v} vs current image {current} -> {'OK' if ok else 'FAIL'}")
    if not ok:
        bad.append('version')
    return bad


SECRET_PATTERNS = [
    ('AWS access key id', re.compile(r'\b(AKIA|ASIA)[0-9A-Z]{16}\b')),
    ('AWS secret-like', re.compile(r'(?<![A-Za-z0-9/+=])(?=[A-Za-z0-9/+]*[A-Z])(?=[A-Za-z0-9/+]*[a-z])'
                                   r'(?=[A-Za-z0-9/+]*[0-9])(?=[A-Za-z0-9/+]*[/+])[A-Za-z0-9/+]{40}(?![A-Za-z0-9/+=])')),
    ('GitLab token', re.compile(r'\bgl(pat|dt|ptt|rt)-[A-Za-z0-9_-]{10,}')),
    ('private key', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('literal secret', re.compile(r'(?i)\b(aws_secret_access_key|secret_key|password|passwd|token)\s*[:=]\s*'
                                  r'["\']?(?!<|\$|\{|os\.|None|null|\'\'|"")[A-Za-z0-9/+_\-]{12,}')),
]


def check_secrets():
    tracked = subprocess.run(['git', 'ls-files'], capture_output=True, text=True, cwd=REPO).stdout.split()
    untracked = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'], capture_output=True, text=True,
                               cwd=REPO).stdout.split()
    files = [f for f in tracked + untracked if f.endswith(DOCS_SCAN) or f.startswith('bin/')]
    files = [f for f in files if not f.startswith('keck_etcs/tests/data/') and (REPO / f).is_file()]
    hits = []
    for f in files:
        try:
            text = (REPO / f).read_text()
        except UnicodeDecodeError:
            continue
        for name, pat in SECRET_PATTERNS:
            for m in pat.finditer(text):
                line = text.count('\n', 0, m.start()) + 1
                hits.append(f'{f}:{line}: {name}')
    print(f'   scanned {len(files)} text files: ' + ('no secret found' if not hits else f'{len(hits)} hit(s)'))
    for h in hits:
        print(f'     {h}')
    return hits


def main():
    bad = []
    print('1. WMKO note against the schemas')
    bad += check_wmko_note()
    print('2. README examples')
    bad += check_readme_examples()
    print('3./4. calibration version, images and pins')
    bad += check_versions_and_images()
    print('5. secrets')
    bad += check_secrets()
    print('ALL CHECKS PASS' if not bad else f'FAILED: {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
