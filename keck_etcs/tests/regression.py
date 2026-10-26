"""Helpers shared by test_regression.py and scripts/regen_regression_fixtures.py (design 6.2)."""
import math

FIXTURES = {'J': 'J_point', 'J2': 'J2_point', 'line': 'J_line'}
"""Fixture name (``tests/data/reference_<name>.json``) -> example (``examples/<example>.json``)."""

RTOL = 1e-6
SIGNIFICANT = 10
IGNORED = {('meta', 'keck_etcs_version')}
"""Paths not compared: a version bump alone does not change results."""


def round_floats(x, sig=SIGNIFICANT):
    """Round every float in a JSON-like structure to ``sig`` significant digits."""
    if isinstance(x, float):
        return float(f'{x:.{sig}g}') if math.isfinite(x) else x
    if isinstance(x, list):
        return [round_floats(v, sig) for v in x]
    if isinstance(x, dict):
        return {k: round_floats(v, sig) for k, v in x.items()}
    return x


def compare(new, old, path=(), rtol=RTOL):
    """Differences between two outputs as strings; numbers compared to ``rtol`` relative."""
    if path in IGNORED:
        return []
    where = '.'.join(map(str, path)) or '(top)'
    if isinstance(old, bool) or isinstance(new, bool) or old is None or new is None or isinstance(old, str):
        return [] if new == old else [f'{where}: {new!r} != {old!r}']
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        if abs(new - old) <= rtol * max(abs(old), abs(new)) or new == old:
            return []
        return [f'{where}: {new!r} != {old!r} (rel {abs(new - old) / max(abs(old), abs(new)):.2e})']
    if isinstance(old, dict) and isinstance(new, dict):
        out = [f'{where}.{k}: missing' for k in old if k not in new]
        out += [f'{where}.{k}: unexpected' for k in new if k not in old]
        for k in old:
            if k in new:
                out += compare(new[k], old[k], path + (k,), rtol)
        return out
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            return [f'{where}: length {len(new)} != {len(old)}']
        out = []
        for i, (a, b) in enumerate(zip(new, old)):
            out += compare(a, b, path + (i,), rtol)
        return out
    return [f'{where}: type {type(new).__name__} != {type(old).__name__}']
