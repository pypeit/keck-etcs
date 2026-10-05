"""keck_etcs.etc: validate and compute (plan step S9, design 5.2-5.3, 6.2)."""
import json

import numpy as np
import pytest

from keck_etcs import etc, schema
from keck_etcs.core import source
from keck_etcs.instruments.mosfire import MOSFIRE


@pytest.fixture(scope='module')
def default():
    return etc.compute({})


def test_validate_fills_defaults_and_names_bad_fields():
    p, w = etc.validate({'source': {'mag': 18}})
    assert p['source'] == {'mag': 18, 'type': 'point', 'mag_system': 'AB', 'size_arcsec': 1.0}
    assert p['readout'] == {'mode': 'MCDS', 'n_reads': 16} and p['band'] == 'J' and w == []
    with pytest.raises(etc.InputError, match=r'slit_width_arcsec: 9'):
        etc.validate({'slit_width_arcsec': 9})
    with pytest.raises(etc.InputError, match='differ in length'):
        etc.validate({'spectrum': {'shape': 'user', 'wave_A': [1.0, 2.0, 3.0], 'flux': [1.0, 2.0]}})
    _, w = etc.validate({'readout': {'mode': 'CDS', 'n_reads': 16}})
    assert any('CDS' in x for x in w)


def test_output_matches_schema_and_is_json(default):
    out = json.loads(json.dumps(default))
    assert schema.errors(out, 'etc_output') == []
    n = len(out['wave_A'])
    for k in ('throughput', 'atm_transmission', 'filter_transmission', 'signal_e', 'sky_e', 'noise_e',
              'snr_pixel', 'snr_resel', 'resolving_power'):
        assert len(out[k]) == n, k
    # no standards yet in the latest era: the nearest era with a curve is used and reported
    assert out['meta']['era'] == '2017-02..2025-02' and out['meta']['inputs']['band'] == 'J'
    assert out['meta']['calib_version'] == 'mosfire-J-2026.10-dev'
    assert out['meta']['pypeit_version'] == '2.0.2.dev1218+g8017f4799'
    assert any('no throughput curve yet for era 2025-04..' in w for w in out['warnings'])
    assert any('held constant' in w for w in out['warnings'])            # J extends past the J2 standard
    assert not any('PROVISIONAL' in w for w in out['warnings'])


def test_window_lsf_and_aperture(default):
    lo, hi = MOSFIRE.band_window('J')
    wave = np.array(default['wave_A'])
    assert wave[0] == lo and wave[-1] <= hi and np.allclose(np.diff(wave), MOSFIRE.bands['J'].dispersion_A_per_pix)
    assert default['n_spec_per_resel'] == pytest.approx(0.7 / 0.277)
    assert default['lsf_fwhm_A'] == pytest.approx(0.7 / 0.277 * 1.2922)
    assert default['n_spatial_pix'] == 6                       # ceil(1.5 x 0.7 / 0.1798)
    assert default['slit_fraction'] == pytest.approx(0.6567, abs=1e-4)


def test_noise_budget_is_consistent(default):
    S, B = np.array(default['signal_e']), np.array(default['sky_e'])
    var = S + 2 * (B + default['dark_e'] + default['read_noise_e'] ** 2)     # ABBA, totals over frames
    np.testing.assert_allclose(np.array(default['noise_e']) ** 2, var, rtol=1e-10)
    np.testing.assert_allclose(default['snr_pixel'], S / np.sqrt(var), rtol=1e-10)
    assert default['read_noise_e'] == pytest.approx(np.sqrt(4 * 6 * 5.8 ** 2))
    assert default['dark_e'] == pytest.approx(4 * 6 * 0.008 * 120)


def test_stare_versus_abba_and_scalings(default):
    stare = etc.compute({'nod': 'stare'})
    assert np.all(np.array(stare['snr_pixel']) >= np.array(default['snr_pixel']))
    assert stare['signal_e'] == default['signal_e']
    double = etc.compute({'throughput': {'scale': 2.0}})
    np.testing.assert_allclose(double['signal_e'], 2 * np.array(default['signal_e']), rtol=1e-12)
    np.testing.assert_allclose(double['sky_e'], 2 * np.array(default['sky_e']), rtol=1e-12)
    sky2 = etc.compute({'sky_scale': 2.0})
    np.testing.assert_allclose(sky2['sky_e'], 2 * np.array(default['sky_e']), rtol=1e-12)


def test_vega_equals_ab_plus_offset():
    off = MOSFIRE.vega_offset('J')
    a = etc.compute({'source': {'mag': 18.0 + off, 'mag_system': 'AB'}})
    v = etc.compute({'source': {'mag': 18.0, 'mag_system': 'Vega'}})
    np.testing.assert_allclose(a['signal_e'], v['signal_e'], rtol=1e-12)


def test_flat_fnu_photon_count_by_hand(default):
    # J = 20 AB flat f_nu: N0 = f_nu c / lam^2 * A * lam / hc
    i = len(default['wave_A']) // 2
    lam = default['wave_A'][i]
    fnu = 10 ** (-0.4 * (20.0 + 48.6))
    n0 = fnu * source.C_A_PER_S / lam ** 2 * MOSFIRE.area_m2 * 1e4 * lam / source.HC_ERG_A
    f_ap = default['slit_fraction'] * default['aperture_fraction']
    expect = n0 * f_ap * default['dispersion_A_per_pix'] * 120 * 4
    # throughput and transmission are LSF-averaged; in a clean region the ratio is their product
    ratio = default['signal_e'][i] / expect
    assert ratio == pytest.approx(default['throughput'][i] * default['atm_transmission'][i], rel=0.02)


@pytest.mark.parametrize('ref', ['pixel', 'resel'])
def test_target_snr_round_trip(ref):
    out = etc.compute({'target_snr': 7.0, 'snr_reference': ref})
    key = 'snr_pixel_median' if ref == 'pixel' else 'snr_resel_median'
    assert out['summary'][key] == pytest.approx(7.0, rel=1e-6)
    # feeding the solved time back reproduces it
    again = etc.compute({'exptime_s': out['summary']['exptime_s']})
    assert again['summary'][key] == pytest.approx(7.0, rel=1e-6)


def test_line_mode():
    inp = {'spectrum': {'shape': 'line', 'line': {'wave_A': 12820.0, 'flux_cgs': 1e-17, 'fwhm_kms': 150}},
           'nod': 'stare', 'exptime_s': 600, 'n_frames': 1}
    out = etc.compute(inp)
    lo, hi = out['summary']['line_window_A']
    assert hi - lo == pytest.approx(np.hypot(12820 * 150 / 299792.458, out['lsf_fwhm_A']))
    # all the line flux lands in the spectrum: total electrons = photons x T x f_ap x t
    i = int(np.argmin(np.abs(np.array(out['wave_A']) - 12820)))
    n_photons = 1e-17 * MOSFIRE.area_m2 * 1e4 * 12820 / source.HC_ERG_A
    f_ap = out['slit_fraction'] * out['aperture_fraction']
    tot = np.sum(out['signal_e'])
    assert tot == pytest.approx(n_photons * f_ap * 600 * out['throughput'][i] * out['atm_transmission'][i], rel=0.03)
    t = etc.compute({**inp, 'target_snr': 5.0, 'snr_reference': 'line'})
    assert t['summary']['snr_line'] == pytest.approx(5.0, rel=1e-6)
    off = etc.compute({**inp, 'spectrum': {'shape': 'line', 'line': {'wave_A': 15000.0, 'flux_cgs': 1e-17}}})
    assert off['summary']['snr_line'] is None and any('outside' in w for w in off['warnings'])


def test_extended_source_tends_to_surface_brightness():
    big = etc.compute({'source': {'type': 'extended', 'mag': 20.0, 'size_arcsec': 20.0},
                       'aperture': {'length_arcsec': 2.0}, 'slit_width_arcsec': 1.0})
    pt = etc.compute({'source': {'type': 'point', 'mag': 20.0}, 'aperture': {'length_arcsec': 50.0},
                      'slit_width_arcsec': 5.0, 'seeing_fwhm_arcsec': 0.3})
    # SB 20 mag/arcsec^2 over a 1" x 2" aperture = a 20 mag point source x 2 (almost all of it passes)
    ratio = np.array(big['signal_e']) / np.array(pt['signal_e'])
    assert np.median(ratio) == pytest.approx(2.0 / (pt['slit_fraction'] * pt['aperture_fraction']), rel=2e-3)


def test_clipping_and_era_warnings():
    out = etc.compute({'airmass': 2.4, 'pwv_mm': 0.6, 'throughput': {'date': '2016-12-01'}})
    w = ' | '.join(out['warnings'])
    assert 'airmass 2.4 clipped' in w and 'pwv_mm 0.6 clipped' in w and 'offline' in w
    assert out['meta']['era'] == '2017-02..2025-02'
    assert any('no throughput curve yet for era 2012-04..2016-09' in x for x in out['warnings'])


def test_seeing_wavelength_scaling():
    out = etc.compute({'seeing_fwhm_arcsec': 0.7, 'seeing_wave_um': 0.5})
    assert out['fwhm_arcsec_band'] == pytest.approx(0.7 * (np.mean(MOSFIRE.band_window('J')) / 5000) ** -0.2)
    fs = np.array(out['slit_fraction'])
    assert fs.size == len(out['wave_A']) and fs[-1] > fs[0]       # seeing improves to the red


def test_user_spectrum_normalization():
    wave = np.linspace(10000, 15000, 501)
    flam = (wave / 1e4) ** -2                                        # flat f_nu
    u = etc.compute({'spectrum': {'shape': 'user', 'wave_A': wave.tolist(), 'flux': (flam * 1e-3).tolist()}})
    f = etc.compute({})
    np.testing.assert_allclose(u['signal_e'], f['signal_e'], rtol=2e-3)


def test_etc_runs_without_pypeit_or_boto3():
    import subprocess
    import sys
    code = ('import sys, socket\n'
            'def _no_net(*a, **k):\n    raise RuntimeError("network access")\n'
            'socket.socket.connect = _no_net\n'
            'from keck_etcs import etc\netc.compute({})\n'
            "print(','.join(m for m in ('pypeit', 'boto3', 'botocore', 'requests') if m in sys.modules))\n")
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ''
