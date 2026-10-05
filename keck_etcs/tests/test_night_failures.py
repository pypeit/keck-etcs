"""nautilus/night_failures.py keeps the optional A0V manifest columns in a sweep manifest (plan S15b)."""
import csv
import importlib.util
from pathlib import Path

from astropy.table import Table

MOD = Path(__file__).resolve().parents[2] / 'nautilus' / 'night_failures.py'


def load():
    spec = importlib.util.spec_from_file_location('night_failures', MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sweep_keeps_a0v_columns(tmp_path, monkeypatch):
    monkeypatch.setenv('KECK_ETCS_DATA', str(tmp_path))
    nf = load()
    st = tmp_path / 'runs' / 'jobx' / 'status'
    st.mkdir(parents=True)
    base = {'job_name': 'jobx', 'instrument': 'mosfire', 'slit': 'LONGSLIT-46x5', 'spec2d': '0', 'notes': '',
            'exit_code': 14, 'error': 'x', 'pod': '', 'node': '', 'image': '', 'image_digest': '', 'time': ''}
    Table(rows=[{**base, 'index': 0, 'night': '20150101', 's3_prefix': 'mosfire/20150101', 'standard': 'HIP 1',
                 'status': 'sens failed', 'std_class': 'A0V', 'jmag_2mass': '7.1', 'std_ra': '10.5',
                 'std_dec': '-3.2'}]).write(st / '0000_20150101.ecsv', format='ascii.ecsv')
    # an older-style row without the optional columns
    Table(rows=[{**base, 'index': 1, 'night': '20150102', 's3_prefix': 'mosfire/20150102', 'standard': 'GD71',
                 'status': 'reduce failed'}]).write(st / '0001_20150102.ecsv', format='ascii.ecsv')
    out = tmp_path / 'sweep.csv'
    assert nf.main('jobx', out=str(out), no_pull=True) == 0
    rows = list(csv.DictReader(open(out)))
    assert list(rows[0])[:7] == list(nf.COLS) and set(nf.OPTIONAL_COLS) <= set(rows[0])
    a0v = [r for r in rows if r['night'] == '20150101'][0]
    assert (a0v['std_class'], a0v['jmag_2mass'], a0v['std_ra'], a0v['std_dec']) == ('A0V', '7.1', '10.5', '-3.2')
    wd = [r for r in rows if r['night'] == '20150102'][0]
    assert wd['std_class'] == '' and wd['standard'] == 'GD71'
