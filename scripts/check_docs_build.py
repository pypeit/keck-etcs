#!/usr/bin/env python
"""Check a built HTML documentation tree (plan S19 Verify).

Usage:
    python scripts/check_docs_build.py [--html docs/_build/html]

Run after ``sphinx-build -W --keep-going -b html docs docs/_build/html``. Standard library only, so it
runs in the docs environment or in ``pypeit14b``. Checks:

1. every expected page exists (the toctree of ``docs/index.md``, the API pages);
2. every page carries the version line, ``keck_etcs <version>`` and ``calibration <calib_version>``,
   read from ``keck_etcs/__init__.py`` and ``keck_etcs/data/index.yaml`` in the repository;
3. every ``<img src>`` and every relative ``<a href>`` (internal links; external URLs are not
   fetched) resolves to a file in the built tree;
4. the report page shows all of the report's figures (as many ``<img>`` as the Markdown has
   images), and the API pages hold the documented objects (``keck_etcs.etc.compute``,
   ``keck_etcs.core.snr``, ``keck_etcs.instruments.mosfire``).

Read-only. Exit 1 on any failure.
"""
import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO = Path(__file__).resolve().parents[1]
PAGES = ['index', 'getting_started', 'examples', 'wmko_api_note', 'field_reference', 'results', 'changes', 'keck_mosfire_design',
         'developer/nautilus', 'keck_mosfire_implementation', 'XTcalc_bug', 'XTcalc_HOWTO',
         'api/index', 'api/etc', 'api/core', 'api/instruments', 'api/calib']
API_OBJECTS = {'api/etc': ['keck_etcs.etc.compute', 'keck_etcs.etc.validate'],
               'api/core': ['keck_etcs.core.snr', 'keck_etcs.core.lsf.fwhm_pix'],
               'api/instruments': ['keck_etcs.instruments.mosfire'],
               'api/calib': ['keck_etcs.calib.combine.combine_era']}
REPORT = REPO / 'reports' / 'Keck_MOSFIRE_report_20261009.md'


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.imgs, self.hrefs, self.ids = [], [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.add(a['id'])
        if tag == 'img' and a.get('src'):
            self.imgs.append(a['src'])
        if tag == 'a' and a.get('href'):
            self.hrefs.append(a['href'])


def expected_versions():
    v = re.search(r'__version__ = "([^"]+)"', (REPO / 'keck_etcs' / '__init__.py').read_text()).group(1)
    cal = sorted(set(re.findall(r'calib_version: (\S+)', (REPO / 'keck_etcs' / 'data' / 'index.yaml').read_text())))
    return v, ', '.join(cal)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--html', default=str(REPO / 'docs' / '_build' / 'html'))
    args = p.parse_args()
    root = Path(args.html)
    bad = []
    version, calib = expected_versions()
    line = re.compile(rf'keck_etcs <strong>{re.escape(version)}</strong>.*calibration\s*<strong>{re.escape(calib)}</strong>',
                      re.S)

    print(f'1./2. pages and version line (keck_etcs {version}, calibration {calib})')
    parsed = {}
    for page in PAGES:
        f = root / f'{page}.html'
        if not f.exists():
            print(f'   MISSING {page}.html')
            bad.append(f'page {page}')
            continue
        text = f.read_text()
        h = Links()
        h.feed(text)
        parsed[page] = (f, h, text)
        ok = bool(line.search(text))
        print(f"   {page}.html: {len(h.imgs)} img, {len(h.hrefs)} links, version line {'OK' if ok else 'MISSING'}")
        if not ok:
            bad.append(f'version line {page}')

    print('3. images and internal links resolve')
    n_img = n_link = 0
    for page, (f, h, _) in parsed.items():
        for src in h.imgs:
            u = urlparse(src)
            if u.scheme or src.startswith('data:'):
                continue
            n_img += 1
            if not (f.parent / unquote(u.path)).resolve().exists():
                print(f'   {page}: image not found: {src}')
                bad.append(f'img {page} {src}')
        for href in h.hrefs:
            u = urlparse(href)
            if u.scheme or href.startswith(('mailto:', '#')) or not u.path:
                continue
            n_link += 1
            target = (f.parent / unquote(u.path)).resolve()
            if not target.exists():
                print(f'   {page}: link not found: {href}')
                bad.append(f'link {page} {href}')
    print(f'   {n_img} images and {n_link} internal links checked')

    print('4. report figures and API objects')
    n_md = len(re.findall(r'!\[[^\]]*\]\([^)]+\)', REPORT.read_text()))
    n_html = len(parsed['results'][1].imgs) if 'results' in parsed else 0
    print(f"   report: {n_md} images in the Markdown, {n_html} on the page -> {'OK' if n_md == n_html else 'FAIL'}")
    if n_md != n_html:
        bad.append('report images')
    for page, objs in API_OBJECTS.items():
        if page not in parsed:
            continue
        for o in objs:
            ok = o in parsed[page][1].ids or f'module-{o}' in parsed[page][1].ids   # module anchors: module-<name>
            print(f"   {page}: {o} {'OK' if ok else 'MISSING'}")
            if not ok:
                bad.append(f'api {o}')
    print('ALL CHECKS PASS' if not bad else f'FAILED: {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
