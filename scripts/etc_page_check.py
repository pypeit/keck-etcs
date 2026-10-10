#!/usr/bin/env python
"""Drive the built interactive ETC page in a real browser and compare with CPython (plan S21 Verify).

Usage (an environment with keck_etcs and Playwright):

    python scripts/etc_page_check.py [--html docs/_build/html] [--browser chrome|firefox]
    python scripts/etc_page_check.py --url https://keck-etcs.readthedocs.io/en/keck-mosfire/etc.html

Serves the built HTML on localhost (or opens ``--url``), opens ``etc.html`` headless in a fresh profile,
presses "Start the calculator", and records the start-up time and the bytes transferred. Then it fills
the form and presses "Compute" for three cases, reading ``window.KECK_ETC`` (set by
``docs/_static/etc.js``):

1. the defaults: ``snr_pixel_median`` equals CPython ``compute()`` of the same inputs to 1e-6, and the
   page shows ``meta.calib_version``;
2. a 10" slit: the page shows the schema message ("Invalid input: ...") and no result;
3. J2, 21 AB, 8 frames, ``target_snr`` 5 per resolution element: ``exptime_s`` equals CPython's.

Also lists every host the page contacted; for the self-hosted site (Q&A S21-2 (b)) that must be the
site's own host only. Exit 1 on any failure.
"""
import argparse
import functools
import http.server
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def serve(directory):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def set_field(page, path, value):
    sel = '#etc-' + path.replace('.', '-')
    el = page.locator(sel)
    if el.evaluate('e => e.tagName') == 'SELECT':
        el.select_option(str(value))
    else:
        el.fill(str(value))
    el.dispatch_event('change')


def run_case(page, fields, timeout):
    page.click('#etc-reset')
    for path, value in fields.items():
        set_field(page, path, value)
    page.evaluate('window.KECK_ETC = undefined')
    page.click('#etc-compute')
    page.wait_for_function('window.KECK_ETC !== undefined', timeout=timeout * 1000)
    return page.evaluate('window.KECK_ETC'), page.inner_text('#etc-results')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--html', default=str(REPO / 'docs' / '_build' / 'html'))
    p.add_argument('--url', help='open this published page instead of serving --html')
    p.add_argument('--browser', default='chrome', choices=['chrome', 'firefox'])
    p.add_argument('--timeout', type=float, default=300.0)
    args = p.parse_args()
    from playwright.sync_api import sync_playwright
    from keck_etcs import etc

    srv = None
    if args.url:
        url = args.url
    else:
        srv = serve(args.html)
        url = f'http://127.0.0.1:{srv.server_address[1]}/etc.html'
    bad = []
    with sync_playwright() as pw:
        browser = (pw.chromium.launch(channel='chrome', headless=True) if args.browser == 'chrome'
                   else pw.firefox.launch(headless=True))
        page = browser.new_context(viewport={'width': 1200, 'height': 1400}).new_page()
        requests = []
        page.on('request', lambda r: requests.append(r.url))
        page.goto(url)
        page.wait_for_function("!document.querySelector('#etc-start').disabled", timeout=60000)
        label = page.inner_text('#etc-start')
        t0 = time.time()
        page.click('#etc-start')
        page.wait_for_function('window.KECK_ETC_READY !== undefined', timeout=args.timeout * 1000)
        ready = page.evaluate('window.KECK_ETC_READY')
        nbytes = page.evaluate("performance.getEntriesByType('resource').reduce((s, e) => s + (e.transferSize || 0), 0)")
        ua = page.evaluate('navigator.userAgent')
        print(f'browser: {ua}')
        print(f'page: {url}')
        print(f'start button: {label!r}')
        print(f'ready after {ready:.1f} s (wall {time.time() - t0:.1f} s); transferred {nbytes / 1e6:.1f} MB')

        # 1. defaults
        r, text = run_case(page, {}, args.timeout)
        ref = etc.compute(r['inputs'])
        a, b = r['output']['summary']['snr_pixel_median'], ref['summary']['snr_pixel_median']
        ok = abs(a / b - 1) <= 1e-6 and ref['meta']['calib_version'] in text
        print(f"1. defaults {r['inputs']}\n   snr_pixel_median page {a!r}, CPython {b!r}; first compute {r['seconds']:.2f} s;"
              f" calib_version {ref['meta']['calib_version']} shown: {ref['meta']['calib_version'] in text} -> "
              f"{'OK' if ok else 'FAIL'}")
        bad += [] if ok else ['defaults']

        # 2. invalid slit
        r, text = run_case(page, {'slit_width_arcsec': 10}, args.timeout)
        try:
            etc.compute(r['inputs'])
            msg = None
        except etc.InputError as exc:
            msg = f'Invalid input: {exc}'
        ok = r['output'] is None and r['error'] == msg and msg in text
        print(f"2. slit 10\": page shows {r['error']!r} -> {'OK' if ok else 'FAIL'}")
        bad += [] if ok else ['invalid']

        # 3. target S/N
        r, text = run_case(page, {'band': 'J2', 'source.mag': 21, 'n_frames': 8, 'target_snr': 5,
                                  'snr_reference': 'resel'}, args.timeout)
        ref = etc.compute(r['inputs'])
        a, b = r['output']['summary']['exptime_s'], ref['summary']['exptime_s']
        ok = abs(a / b - 1) <= 1e-6
        print(f"3. target {r['inputs']}\n   exptime_s page {a!r}, CPython {b!r} ({r['seconds']:.2f} s) -> "
              f"{'OK' if ok else 'FAIL'}")
        bad += [] if ok else ['target']
        browser.close()
    if srv:
        srv.shutdown()
    hosts = sorted({u.split('/')[2] for u in requests if u.startswith('http')})
    own = url.split('/')[2]
    ok = hosts == [own]
    print(f"hosts contacted: {hosts} -> {'OK (self-hosted only)' if ok else 'FAIL (third-party request)'}")
    bad += [] if ok else ['hosts']
    print('ALL CHECKS PASS' if not bad else f'FAILED: {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
