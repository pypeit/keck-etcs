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
    'myst_nb',             # includes myst_parser; executes docs/examples.md at build time
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.mathjax',
]
source_suffix = {'.md': 'myst-nb', '.rst': 'restructuredtext'}
root_doc = 'index'
# Planning and working documents that are not pages of the site
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store', 'requirements.txt', 'jupyter_execute',
                    '_generated/*.md']   # generated files are included by their pages, not pages themselves

# ---- generated pages (plan S20): the field reference tables, from the JSON schemas, at every build
sys.path.insert(0, str(REPO / 'scripts'))
import gen_field_reference  # noqa: E402
print(f'[keck_etcs docs] field reference: {gen_field_reference.write(DOCS / "_generated" / "field_reference_tables.md")}')

# ---- interactive ETC page (plan S21; docs/etc.md, docs/_static/etc.js): self-hosted Pyodide (Q&A S21-2 (b)),
# the keck_etcs wheel of this very source tree, and the input schema, all as static files of the site
import json as _json  # noqa: E402
import shutil as _shutil  # noqa: E402
import fetch_pyodide  # noqa: E402

_STATIC_GEN = DOCS / '_generated' / 'static'
_pyo_dir = fetch_pyodide.fetch(_STATIC_GEN / 'pyodide', log=print)
_wheel_dir = _STATIC_GEN / 'wheels'
_shutil.rmtree(_wheel_dir, ignore_errors=True)
subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '-q', '-w', str(_wheel_dir), str(REPO)], check=True)
_wheel = next(_wheel_dir.glob(f'keck_etcs-{keck_etcs.__version__}-*.whl'))
_shutil.copy2(REPO / 'keck_etcs' / 'schema' / 'etc_input.json', _STATIC_GEN / 'etc_input.json')
_pyo_lock = _json.loads((_pyo_dir / 'pyodide-lock.json').read_text())
_download_mb = (sum(f.stat().st_size for f in _pyo_dir.iterdir() if f.is_file() and f.name != 'pyodide-lock.json')
                + _wheel.stat().st_size) / 1e6
(_STATIC_GEN / 'etc_config.json').write_text(_json.dumps({
    'pyodide_version': fetch_pyodide.VERSION,
    'pyodide_index': f'pyodide/v{fetch_pyodide.VERSION}/',
    'pyodide_python': _pyo_lock['info']['python'],
    'packages': fetch_pyodide.PACKAGES,
    'wheel': f'wheels/{_wheel.name}',
    'keck_etcs_version': keck_etcs.__version__,
    'calib_version': CALIB_VERSION,
    'download_mb': round(_download_mb, 1),
}, indent=1))
print(f'[keck_etcs docs] interactive page: wheel {_wheel.name}, first-load download about {_download_mb:.0f} MB')

# ---- executed examples (myst-nb): always run, so every number on the page comes from this build
nb_execution_mode = 'force'
nb_execution_raise_on_error = True
nb_execution_timeout = 300
nb_merge_streams = True

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
html_static_path = ['_static', '_generated/static']
html_css_files = ['etc.css']
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
