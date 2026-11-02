"""Filter rules of scripts/nautilus/backup_products.py (D39, D55 band directories)."""
import importlib.util
from pathlib import Path

MOD = Path(__file__).resolve().parents[2] / 'scripts' / 'nautilus' / 'backup_products.py'


def load():
    spec = importlib.util.spec_from_file_location('backup_products', MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_filter_rules_cover_night_and_band_layouts():
    bp = load()
    rules = bp.filter_rules(['mosfire/20141005'])
    # legacy J products at the night level, H under H/, raw manifest once
    assert '+ /mosfire/20141005/sens/**' in rules
    assert '+ /mosfire/20141005/[A-Z]*/sens/**' in rules
    assert '+ /mosfire/20141005/[A-Z]*/gates.json' in rules
    assert rules.count('+ /mosfire/20141005/raw/manifest.ecsv') == 1
    assert rules[-1] == '- **'
    assert '+ /manifests/**' in rules and '+ /runs/**' in rules
    # a band prefix: only that band, plus the night-level raw manifest
    rules = bp.filter_rules(['mosfire/20140606/H'], roots=False)
    assert '+ /mosfire/20140606/H/redux/Science/spec1d_*' in rules
    assert '+ /mosfire/20140606/raw/manifest.ecsv' in rules
    assert not any(r.startswith('+ /mosfire/20140606/sens') for r in rules)
    assert not any('[A-Z]' in r for r in rules)
    # nights -> every band
    assert '+ /mosfire/20220409/[A-Z]*/harvest/**' in bp.filter_rules(nights=['20220409'])


def test_release_prefixes_keep_the_band(monkeypatch):
    bp = load()
    pre = bp.release_prefixes()
    assert 'mosfire/20141005/H' in pre and 'mosfire/20220409' in pre
    assert 'mosfire/20140606/H' not in pre      # excluded_nonlinear
    assert all(p.startswith('mosfire/') for p in pre)
