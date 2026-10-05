"""JSON Schemas (draft 2020-12) of the ETC input and output: the contract with WMKO (design 5.2).

``etc.validate`` (S9) applies them and fills defaults.
"""
import json
from functools import lru_cache
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load(name):
    """Return the schema ``'etc_input'`` or ``'etc_output'`` as a dict."""
    return json.loads((SCHEMA_DIR / f'{name}.json').read_text())


def errors(instance, name='etc_input'):
    """Schema violations of ``instance``, each message prefixed with the offending field's path.

    Returns:
        list: Strings such as ``"slit_width_arcsec: 7.0 is greater than the maximum of 5.0"``;
        empty if ``instance`` is valid.
    """
    from jsonschema import Draft202012Validator
    v = Draft202012Validator(load(name))
    out = []
    for e in sorted(v.iter_errors(instance), key=lambda e: list(e.absolute_path)):
        field = '.'.join(str(p) for p in e.absolute_path) or '(top level)'
        out.append(f'{field}: {e.message}')
    return out
