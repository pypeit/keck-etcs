"""The input and output JSON Schemas (design 5.2, 6.2)."""
import copy

import pytest
from jsonschema import Draft202012Validator

from keck_etcs import schema


@pytest.mark.parametrize('name', ['etc_input', 'etc_output'])
def test_schemas_are_valid_and_accept_their_examples(name):
    s = schema.load(name)
    Draft202012Validator.check_schema(s)
    assert s['examples']
    for ex in s['examples']:
        assert schema.errors(ex, name) == []


def test_every_input_field_has_a_default_or_is_conditional():
    props = schema.load('etc_input')['properties']
    expected = {'instrument', 'band', 'slit_width_arcsec', 'source', 'spectrum', 'seeing_fwhm_arcsec',
                'seeing_wave_um', 'exptime_s', 'n_frames', 'readout', 'nod', 'airmass', 'pwv_mm',
                'sky_scale', 'aperture', 'throughput', 'target_snr', 'snr_reference'}
    assert set(props) == expected
    for k, v in props.items():
        assert 'default' in v, k
    for k, v in props['source']['properties'].items():
        assert 'default' in v, k


@pytest.mark.parametrize('bad, field', [
    ({'slit_width_arcsec': 7.0}, 'slit_width_arcsec'),
    ({'airmass': 3.0}, 'airmass'),
    ({'exptime_s': 1.0}, 'exptime_s'),
    ({'readout': {'n_reads': 12}}, 'readout.n_reads'),
    ({'source': {'mag': 40}}, 'source.mag'),
    ({'spectrum': {'line': {'wave_A': 12800.0, 'flux_cgs': 1e-17, 'fwhm_kms': 1.0}}}, 'spectrum.line.fwhm_kms'),
    ({'band': 'K'}, 'band'),
    ({'throughput': {'date': '22-04-09'}}, 'throughput.date'),
])
def test_out_of_range_field_is_rejected_by_name(bad, field):
    errs = schema.errors(bad)
    assert len(errs) == 1 and errs[0].startswith(field + ':'), errs


def test_unknown_and_missing_conditional_fields():
    errs = schema.errors({'slit_width': 0.7})
    assert len(errs) == 1 and "'slit_width'" in errs[0]
    assert schema.errors({'spectrum': {'shape': 'user', 'wave_A': [1.0, 2.0]}})[0].startswith('spectrum:')
    assert schema.errors({'spectrum': {'shape': 'line'}})[0].startswith('spectrum:')


def test_output_schema_requires_the_design_fields():
    ex = copy.deepcopy(schema.load('etc_output')['examples'][0])
    del ex['saturation']['flag']
    assert schema.errors(ex, 'etc_output')[0].startswith('saturation:')
    ex = copy.deepcopy(schema.load('etc_output')['examples'][0])
    ex['saturation']['flag'] = 'bad'
    assert schema.errors(ex, 'etc_output')[0].startswith('saturation.flag:')
