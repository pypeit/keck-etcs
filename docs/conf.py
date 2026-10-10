"""Sphinx configuration for the keck_etcs documentation (plan S19; Read the Docs, ``.readthedocs.yaml``).

Build locally, in an environment with ``docs/requirements.txt`` and ``pip install .`` (no extras, no PypeIt):

    sphinx-build -W --keep-going -b html docs docs/_build/html

The existing Markdown documents (``docs/*.md``, ``README.md``, ``CHANGES.md``, the report and the
Nautilus operator guide) are the sources; the pages here include them, they are not copied.
Every page carries a version line (keck_etcs version and calibration release) computed below from
``keck_etcs.__version__`` and ``keck_etcs/data/index.yaml``.
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import yaml

DOCS = Path(__file__).resolve().parent
REPO = DOCS.parent

import keck_etcs  # noqa: E402  (the installed package, as on Read the Docs)

# ---- prove the build needs no PypeIt (plan S19 Verify)
_HAS_PYPEIT = importlib.util.find_spec('pypeit') is not None
print(f'[keck_etcs docs] keck_etcs {keck_etcs.__version__} from {keck_etcs.__file__}')
print(f'[keck_etcs docs] PypeIt importable in the build environment: {_HAS_PYPEIT}')
try:
    _pip = subprocess.run([sys.executable, '-m', 'pip', 'list', '--format=freeze'], capture_output=True,
                          text=True, timeout=120).stdout
    print('[keck_etcs docs] pip list:\n' + _pip)
except Exception as exc:  # pip list is informational only
    print(f'[keck_etcs docs] pip list failed: {exc}')
if _HAS_PYPEIT and not os.environ.get('KECK_ETCS_DOCS_ALLOW_PYPEIT'):
    raise RuntimeError('PypeIt is importable: build the docs in an environment without it (docs/requirements.txt '
                       'plus `pip install .`), or set KECK_ETCS_DOCS_ALLOW_PYPEIT=1 for a local preview.')


def _calib_version():
    index = yaml.safe_load((Path(keck_etcs.__file__).parent / 'data' / 'index.yaml').read_text())['files']
    versions = sorted({v['calib_version'] for v in index.values()})
    return ', '.join(versions)


CALIB_VERSION = _calib_version()

# ---- project
project = 'keck_etcs'
author = 'J. Xavier Prochaska and the keck-etcs contributors'
copyright = '2026, PypeIt'
release = version = keck_etcs.__version__

# ---- extensions
extensions = [
    'myst_parser',
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.mathjax',
]
source_suffix = {'.md': 'markdown', '.rst': 'restructuredtext'}
root_doc = 'index'
# Planning and working documents that are not pages of the site
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store', 'requirements.txt']

myst_enable_extensions = ['colon_fence', 'deflist']
myst_heading_anchors = 4

autodoc_default_options = {'members': True, 'undoc-members': False, 'show-inheritance': True}
autodoc_member_order = 'bysource'
autodoc_typehints = 'description'
# keck_etcs.calib imports PypeIt and matplotlib only inside functions; mock them for any module-level use
autodoc_mock_imports = ['pypeit', 'matplotlib', 'boto3', 'IPython']
napoleon_google_docstring = True
napoleon_numpy_docstring = False

# ---- HTML
html_theme = 'furo'
html_title = f'keck_etcs {version}'
html_static_path = []
VERSION_LINE = (f'keck_etcs <strong>{version}</strong> &middot; calibration '
                f'<strong>{CALIB_VERSION}</strong> &middot; MOSFIRE J/J2')
html_theme_options = {
    'announcement': VERSION_LINE,
    'source_repository': 'https://github.com/pypeit/keck-etcs/',
    'source_branch': os.environ.get('READTHEDOCS_GIT_IDENTIFIER', 'main'),
    'source_directory': 'docs/',
}
# the same line, for templates and for the S19 check script
html_context = {'keck_etcs_version': version, 'calib_version': CALIB_VERSION}
print(f'[keck_etcs docs] version line: keck_etcs {version} / calibration {CALIB_VERSION}')
