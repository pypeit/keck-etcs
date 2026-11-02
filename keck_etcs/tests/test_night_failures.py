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
    assert list(rows[0])[:7] == list(nf.COLS) and {'std_class', 'jmag_2mass', 'std_ra', 'std_dec'} <= set(rows[0])
    assert 'filter' not in rows[0]          # optional columns appear only when some row has a value
    a0v = [r for r in rows if r['night'] == '20150101'][0]
    assert (a0v['std_class'], a0v['jmag_2mass'], a0v['std_ra'], a0v['std_dec']) == ('A0V', '7.1', '10.5', '-3.2')
    wd = [r for r in rows if r['night'] == '20150102'][0]
    assert wd['std_class'] == '' and wd['standard'] == 'GD71'


def test_sweep_manifest_filter_and_retry_data(tmp_path, monkeypatch):
    """S24b: rows are keyed by (night, band); --manifest restricts the sweep to a batch's rows and
    --retry-data retries the data failures that the history rule would otherwise drop."""
    monkeypatch.setenv('KECK_ETCS_DATA', str(tmp_path))
    nf = load()
    st = tmp_path / 'runs' / 'jobx' / 'status'
    st.mkdir(parents=True)
    base = {'job_name': 'jobx', 'instrument': 'mosfire', 'slit': 'long2pos_specphot', 'spec2d': '0', 'notes': '',
            'exit_code': 10, 'error': 'no flats', 'pod': '', 'node': '', 'image': '', 'image_digest': '',
            'standard': 'HD1', 'status': 'no calibs'}
    rows = [{**base, 'index': 0, 'night': '20150101', 's3_prefix': 'mosfire/20150101', 'band': 'J', 'time': '1'},
            {**base, 'index': 1, 'night': '20150101', 's3_prefix': 'mosfire/20150101/H', 'band': 'H', 'time': '2'},
            {**base, 'index': 2, 'night': '20150102', 's3_prefix': 'mosfire/20150102/H', 'band': 'H', 'time': '3'},
            {**base, 'index': 3, 'night': '20150103', 's3_prefix': 'mosfire/20150103/H', 'band': 'H', 'time': '4',
             'status': 'success', 'exit_code': 0, 'error': ''}]
    for i, r in enumerate(rows):
        Table(rows=[r]).write(st / f'{i:04d}.ecsv', format='ascii.ecsv')
    # an earlier data failure of 20150102 H under another job: two strikes
    old = tmp_path / 'runs' / 'joby' / 'status'
    old.mkdir(parents=True)
    Table(rows=[{**rows[2], 'job_name': 'joby', 'time': '0'}]).write(old / '0000.ecsv', format='ascii.ecsv')
    man = tmp_path / 'batch.csv'
    man.write_text('night,band\n20150102,H\n20150101,H\n20150103,H\n20150104,H\n')
    out = tmp_path / 'sweep.csv'
    assert nf.main('jobx', out=str(out), no_pull=True, manifest=str(man)) == 0
    got = [(r['night'], r['band']) for r in csv.DictReader(open(out))]
    assert got == [('20150101', 'H')]            # 20150102 dead (two strikes), 20150103 success, no J row
    assert nf.main('jobx', out=str(out), no_pull=True, manifest=str(man), retry_data=True) == 0
    got = [(r['night'], r['band']) for r in csv.DictReader(open(out))]
    assert got == [('20150102', 'H'), ('20150101', 'H')]     # manifest order
    assert nf.main('jobx', out=str(out), no_pull=True) == 0
    assert sorted((r['night'], r['band']) for r in csv.DictReader(open(out))) == [('20150101', 'H'), ('20150101', 'J')]
