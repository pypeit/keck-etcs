#!/usr/bin/env python
"""Run keck_etcs.etc.compute in Pyodide in a real browser and compare with CPython (plan S21).

Usage (in an environment with keck_etcs and Playwright; browsers are the system's Chrome and, with
``--browser firefox``, Playwright's Firefox):

    python scripts/pyodide_check.py --wheel dist/keck_etcs-<v>-py3-none-any.whl [--pyodide 314.0.7]
        [--browser chrome|firefox] [--cases default,target,invalid] [--index-url URL] [--log-requests]

``--index-url`` points Pyodide at a self-hosted copy (``scripts/fetch_pyodide.py``; e.g. the built docs'
``_static/pyodide/``) instead of the CDN; ``--log-requests`` prints every URL the page fetched, which
must then all be on localhost for a self-hosted run.

Writes a small test page next to a copy of the wheel in a temporary directory, serves it with
``http.server`` on localhost, and opens it headless. The page loads Pyodide ``--pyodide`` from the
jsDelivr CDN, ``loadPackage``s numpy, scipy, astropy, pyyaml and jsonschema (their dependencies
follow from ``pyodide-lock.json``), installs the wheel with micropip, and runs the cases:

- ``default``: ``compute({})``;
- ``target``: J2, 21 AB, 8 frames, ``target_snr`` 5 per resolution element;
- ``invalid``: a 10" slit, which must raise ``InputError`` with the schema message.

Reports each stage's wall-clock (Pyodide start, packages, wheel, first compute, second compute), the
bytes transferred (Resource Timing ``transferSize``, 0 for cache hits; a fresh browser profile is used,
so the first run is cold), and the comparison with CPython ``compute()`` on the same inputs:
``snr_pixel_median`` and ``exptime_s`` to 1e-6 relative. Exit 1 on a mismatch or a failure.
"""
import argparse
import functools
import http.server
import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path

CASES = {
    'default': {},
    'target': {'band': 'J2', 'source': {'mag': 21.0}, 'n_frames': 8, 'target_snr': 5, 'snr_reference': 'resel'},
    'invalid': {'slit_width_arcsec': 10.0},
}
PACKAGES = ['numpy', 'scipy', 'astropy', 'pyyaml', 'jsonschema', 'micropip']

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>pyodide check</title>
<script src="{index_url}pyodide.js"></script></head><body>
<pre id="log"></pre>
<script>
const T0 = performance.now(); const stages = {{}};
const mark = (k) => {{ stages[k] = (performance.now() - T0) / 1000; }};
async function run() {{
  const py = await loadPyodide({{indexURL: new URL('{index_url}', location.href).href}}); mark('pyodide_ready');
  await py.loadPackage({packages}); mark('packages_loaded');
  const micropip = py.pyimport('micropip');
  await micropip.install(new URL('{wheel}', location.href).href); mark('wheel_installed');
  py.globals.set('CASES_JSON', {cases_json});
  const out = py.runPython(`
import json, time
from keck_etcs import etc
res = {{}}
for name, inp in json.loads(CASES_JSON).items():
    t = time.perf_counter()
    try:
        o = etc.compute(inp)
        res[name] = {{'ok': True, 'summary': o['summary'], 'meta': {{k: o['meta'][k] for k in ('keck_etcs_version', 'calib_version', 'era')}},
                     'warnings': o['warnings'], 'seconds': time.perf_counter() - t}}
    except etc.InputError as exc:
        res[name] = {{'ok': False, 'error': str(exc), 'seconds': time.perf_counter() - t}}
json.dumps(res)
`); mark('computed');
  const bytes = performance.getEntriesByType('resource').reduce((s, e) => s + (e.transferSize || 0), 0);
  window.RESULT = {{stages, bytes, results: JSON.parse(out), ua: navigator.userAgent}};
}}
run().catch(e => {{ window.RESULT = {{error: String(e), stages}}; }});
</script></body></html>"""


def serve(directory):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--wheel', required=True)
    p.add_argument('--pyodide', default='314.0.7')
    p.add_argument('--browser', default='chrome', choices=['chrome', 'firefox'])
    p.add_argument('--cases', default='default,target,invalid')
    p.add_argument('--timeout', type=float, default=300.0, help='seconds')
    p.add_argument('--index-url', help='self-hosted Pyodide directory URL (ends with /); default: jsDelivr CDN')
    p.add_argument('--serve-dir', help='also serve this directory at /site/ (e.g. the built docs html)')
    p.add_argument('--log-requests', action='store_true')
    args = p.parse_args()
    from playwright.sync_api import sync_playwright
    from keck_etcs import etc

    cases = {k: CASES[k] for k in args.cases.split(',')}
    tmp = Path(tempfile.mkdtemp(prefix='pyodide_check_'))
    wheel = Path(args.wheel)
    shutil.copy2(wheel, tmp / wheel.name)
    if args.serve_dir:
        (tmp / 'site').symlink_to(Path(args.serve_dir).resolve())
    index_url = args.index_url or f'https://cdn.jsdelivr.net/pyodide/v{args.pyodide}/full/'
    (tmp / 'index.html').write_text(PAGE.format(index_url=index_url, packages=json.dumps(PACKAGES),
                                                wheel=wheel.name, cases_json=json.dumps(json.dumps(cases))))
    srv = serve(tmp)
    url = f'http://127.0.0.1:{srv.server_address[1]}/index.html'
    bad = []
    with sync_playwright() as pw:
        if args.browser == 'chrome':
            browser = pw.chromium.launch(channel='chrome', headless=True)
        else:
            browser = pw.firefox.launch(headless=True)
        page = browser.new_context().new_page()
        requests = []
        page.on('request', lambda req: requests.append(req.url))
        page.goto(url)
        page.wait_for_function('window.RESULT !== undefined', timeout=args.timeout * 1000)
        r = page.evaluate('window.RESULT')
        browser.close()
    srv.shutdown()
    hosts = sorted({u.split('/')[2] for u in requests if '://' in u})
    print(f'requests: {len(requests)} to hosts {hosts}')
    if args.log_requests:
        for u in requests:
            print('   ', u)
    if 'error' in r:
        print(f"PYODIDE FAILED: {r['error']} (stages {r.get('stages')})")
        return 1
    st = r['stages']
    print(f"browser: {r['ua']}")
    print(f"Pyodide {args.pyodide}; wheel {wheel.name} ({wheel.stat().st_size / 1e6:.2f} MB)")
    print(f"stages [s]: pyodide {st['pyodide_ready']:.1f}, packages {st['packages_loaded']:.1f}, "
          f"wheel {st['wheel_installed']:.1f}, cases done {st['computed']:.1f}")
    print(f"transferred: {r['bytes'] / 1e6:.1f} MB")
    for name, inp in cases.items():
        res = r['results'][name]
        try:
            ref = etc.compute(inp)
        except etc.InputError as exc:
            ok = (not res['ok']) and res['error'] == str(exc)
            print(f"{name}: InputError in both -> {'OK' if ok else 'FAIL'}: {res.get('error')!r}")
            bad += [] if ok else [name]
            continue
        if not res['ok']:
            print(f"{name}: Pyodide raised {res['error']!r} -> FAIL")
            bad.append(name)
            continue
        for key in ('snr_pixel_median', 'exptime_s'):
            a, b = res['summary'][key], ref['summary'][key]
            ok = abs(a / b - 1) <= 1e-6
            print(f"{name}: {key} Pyodide {a!r} CPython {b!r} rel {abs(a / b - 1):.1e} -> {'OK' if ok else 'FAIL'}")
            bad += [] if ok else [f'{name} {key}']
        print(f"{name}: meta {res['meta']}, {len(res['warnings'])} warnings, compute {res['seconds']:.2f} s")
    print('ALL CHECKS PASS' if not bad else f'FAILED: {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
