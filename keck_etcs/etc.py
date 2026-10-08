"""The public entry point: ``compute(inputs: dict) -> dict`` (design 5.2, 5.3).

``validate`` checks the inputs against ``keck_etcs/schema/etc_input.json``,
fills defaults and collects warnings; ``compute`` returns every output field
of ``etc_output.json``. Inputs and outputs are plain JSON-serializable dicts.
Out-of-range physics is clipped with a warning, never raised; only inputs
that violate the schema raise :class:`InputError`. No PypeIt, no network.

Method (design 5.3): on the sky grid's uniform 0.5 A vacuum grid around the
band window, the source photon rate N0 (5.3.2) is multiplied by the
atmospheric transmission (5.3.3) and the system throughput (5.3.4, the
filter-free era curve times the band's filter times ``throughput.scale``;
completed from the nearest era that measured the rest of the window,
scaled to this era in 11900-12450 A, else held constant beyond the curve's
measured range, with a warning),
convolved with the Gaussian LSF (5.3.6) and sampled at the pixel centres.
The product is convolved, rather than each factor separately, so that a
line on a telluric feature is handled correctly; for a smooth source the two
agree. The sky (5.3.8) is ``sky_scale * B * T_sys`` convolved the same way,
without T_atm (N6). Slit loss and aperture follow 5.3.5, the noise 5.3.9-10,
the exposure-time solution N7, saturation 5.3.11.

Extended sources: ``source.mag`` is per arcsec^2 and, in line mode, the
line flux is per arcsec^2 too; the flux of the disk (``size_arcsec``) is
surface brightness x pi D^2 / 4, of which ``extended_fraction`` enters the
aperture.
"""
import copy

import numpy as np

import keck_etcs
from keck_etcs import instruments, schema
from keck_etcs.core import atmosphere, lsf, slitloss, snr, sky, source

MARGIN_FWHM = 10.0
"""Fine-grid margin around the band window, in LSF FWHMs."""

PERSISTENCE_WARNING = ('the brightest pixel is beyond the 1 percent linearity limit; persistence '
                       '(~0.04 percent, ~10 min) is not modeled')


class InputError(ValueError):
    """Inputs violate the schema; the message names every offending field."""


def _fill_defaults(inst, sch):
    for key, prop in sch.get('properties', {}).items():
        if key not in inst and 'default' in prop:
            inst[key] = copy.deepcopy(prop['default'])
        if isinstance(inst.get(key), dict) and prop.get('type') == 'object':
            _fill_defaults(inst[key], prop)
    return inst


def validate(inputs):
    """Check ``inputs`` against the schema, fill defaults and collect warnings.

    Args:
        inputs (dict): ETC inputs (``etc_input.json``).

    Returns:
        tuple: ``(filled, warnings)``; ``filled`` is a new dict with every
        default in place.

    Raises:
        InputError: listing each schema violation by field name.
    """
    errs = schema.errors(inputs)
    if errs:
        raise InputError('; '.join(errs))
    p = _fill_defaults(copy.deepcopy(inputs), schema.load('etc_input'))
    warnings = []
    spec = p['spectrum']
    if p['readout']['mode'] == 'CDS' and p['readout']['n_reads'] != 1:
        warnings.append(f"readout.n_reads {p['readout']['n_reads']} ignored for CDS (uses 1)")
    if spec['shape'] != 'line' and 'line' in spec:
        warnings.append(f"spectrum.line ignored for spectrum.shape = {spec['shape']}")
    if spec['shape'] != 'user' and ('wave_A' in spec or 'flux' in spec):
        warnings.append(f"spectrum.wave_A/flux ignored for spectrum.shape = {spec['shape']}")
    if spec['shape'] == 'user' and len(spec['wave_A']) != len(spec['flux']):
        raise InputError(f"spectrum: wave_A ({len(spec['wave_A'])}) and flux ({len(spec['flux'])}) differ in length")
    if p['snr_reference'] == 'line' and spec['shape'] != 'line':
        warnings.append('snr_reference = line needs spectrum.shape = line; using pixel')
    if p['source']['type'] == 'extended' and p['aperture']['length_arcsec'] is None:
        warnings.append('extended source: the aperture length is aperture.length_fwhm x the seeing FWHM; '
                        'set aperture.length_arcsec to match the source')
    if p['source']['type'] == 'extended' and spec['shape'] == 'line':
        warnings.append('extended source: spectrum.line.flux_cgs is taken per arcsec^2')
    if p['target_snr'] is None and p['snr_reference'] != 'pixel':
        warnings.append('snr_reference has no effect without target_snr')
    return p, warnings


def _source_flambda(p, inst, band, fw):
    """Source f_lambda on the fine grid (per arcsec^2 for an extended source), and warnings."""
    spec, src, warnings = p['spectrum'], p['source'], []
    filt = inst.filter_curve(band)
    vega = inst.vega_offset(band)

    def scaled(shape_fn, mag):
        # normalize on the filter's own grid, so the band is covered whatever the fine grid
        fnu = source.mean_fnu(filt['wave_A'], shape_fn(filt['wave_A']), filt['wave_A'], filt['transmission'])
        target = 10 ** (-0.4 * (source.to_ab(mag, src['mag_system'], vega) + source.AB_ZEROPOINT))
        if not fnu > 0:
            raise InputError('spectrum: the user spectrum has no flux in the band')
        return shape_fn(fw) * (target / fnu)

    if spec['shape'] == 'line':
        line = spec['line']
        f = source.gaussian_line_binned(fw, line['wave_A'], line['flux_cgs'],
                                        source.line_fwhm_A(line['wave_A'], line['fwhm_kms']))
        if line.get('continuum_mag') is not None:
            f = f + scaled(lambda w: source.shape_flambda(w, 'flat_fnu'), line['continuum_mag'])
        return f, warnings
    if spec['shape'] == 'user':
        uw = np.asarray(spec['wave_A'], float)
        lo, hi = filt['meta']['half_power_A']
        if uw.min() > lo or uw.max() < hi:
            warnings.append(f'the user spectrum ({uw.min():.0f}-{uw.max():.0f} A) does not cover the {band} half-power '
                            f'band ({lo:.0f}-{hi:.0f} A); it is zero outside its range')
        fn = lambda w: source.shape_flambda(w, 'user', user_wave=spec['wave_A'], user_flux=spec['flux'])
    else:
        fn = lambda w: source.shape_flambda(w, spec['shape'], alpha=spec['alpha'])
    return scaled(fn, src['mag']), warnings


def _fractions(p, inst, fwhm, length):
    """Slit-loss quantities for one seeing FWHM (point or extended source)."""
    w, ps, beta = p['slit_width_arcsec'], inst.platescale, inst.moffat_beta
    if p['source']['type'] == 'point':
        q = slitloss.aperture_quantities(fwhm, w, length, ps, beta)
        return q['slit_fraction'], q['f_slit_ap'], q['f_peak']
    d = p['source']['size_arcsec']
    long_ap = max(1000.0, 10.0 * (d + fwhm))
    return (slitloss.extended_fraction(fwhm, w, long_ap, d, beta), slitloss.extended_fraction(fwhm, w, length, d, beta),
            slitloss.extended_fraction(fwhm, w, ps, d, beta))


def _tolist(x):
    a = np.asarray(x, float)
    return float(a) if a.ndim == 0 else a.tolist()


def compute(inputs):
    """Run the ETC.

    Args:
        inputs (dict): ETC inputs (``etc_input.json``); missing fields take
            their defaults.

    Returns:
        dict: Every field of ``etc_output.json``.

    Raises:
        InputError: if the inputs violate the schema.
    """
    p, warnings = validate(inputs)
    inst = instruments.get(p['instrument'])
    band = p['band']

    # ---- pixel grid, LSF (5.3.6)
    lo, hi = inst.band_window(band)
    dlam = inst.bands[band].dispersion_A_per_pix
    wave = lsf.pixel_grid(lo, hi, dlam)
    w = p['slit_width_arcsec']
    fwhm_pix, lsf_source = inst.lsf_fwhm_pix(w)
    if not lsf_source.startswith('measured'):
        warnings.append(f'LSF for a {w}" slit from the interim rule {lsf_source}; only measured slit widths are exact')
    fwhm_A = fwhm_pix * dlam

    # ---- fine grid: atmosphere, sky, throughput (5.3.3, 5.3.4, 5.3.8)
    g = inst.sky_grid()
    sel = (g['wave_A'] >= lo - MARGIN_FWHM * fwhm_A) & (g['wave_A'] <= hi + MARGIN_FWHM * fwhm_A)
    fw = g['wave_A'][sel]
    t_atm, w1 = atmosphere.transmission(g['trans'][:, sel], g['airmass'], g['pwv_mm'], p['airmass'], p['pwv_mm'])
    b_sky, _ = sky.sky_background(g['skybg'][:, sel], g['airmass'], g['pwv_mm'], p['airmass'], p['pwv_mm'],
                                  p['sky_scale'])
    warnings += w1
    filt = inst.filter_curve(band)
    f_filt = np.interp(fw, filt['wave_A'], filt['transmission'], left=0.0, right=0.0)
    era, w2 = inst.era_for_date(p['throughput']['date'])
    warnings += w2
    th = inst.throughput_for_window(era, lo, hi, margin=fwhm_A)
    warnings += th['warnings']
    era = th['era']
    t_lo, t_hi = th['covered_A']
    if lo < t_lo - fwhm_A or hi > t_hi + fwhm_A:          # more than one LSF FWHM uncovered
        warnings.append(f'throughput measured over {t_lo:.0f}-{t_hi:.0f} A ({th["file"]}); held constant at the edge '
                        f'value over the rest of the {band} window ({lo:.0f}-{hi:.0f} A)')
    t_sys = np.interp(fw, th['wave_A'], th['thru']) * f_filt * p['throughput']['scale']

    # ---- source (5.3.1, 5.3.2)
    flam, w3 = _source_flambda(p, inst, band, fw)
    warnings += w3
    if p['source']['type'] == 'extended':
        flam = flam * np.pi * p['source']['size_arcsec'] ** 2 / 4.0
    n0 = source.photon_rate(fw, flam, inst.area_m2 * 1e4)

    obj = lsf.convolve_to_pixels(fw, n0 * t_atm * t_sys, fwhm_A, wave)       # photons/s/A at the slit
    b = sky.sky_rate_per_pixel(lsf.convolve_to_pixels(fw, b_sky * t_sys, fwhm_A, wave), inst.area_m2, 1.0, w,
                               inst.platescale, dlam)                         # e-/s per (spatial, spectral) pix
    thru_pix = lsf.convolve_to_pixels(fw, t_sys, fwhm_A, wave)
    atm_pix = lsf.convolve_to_pixels(fw, t_atm, fwhm_A, wave)
    filt_pix = lsf.convolve_to_pixels(fw, f_filt, fwhm_A, wave)

    # ---- seeing, slit loss and aperture (5.3.5, D26)
    center = 0.5 * (lo + hi)
    s_band = float(slitloss.seeing_at(p['seeing_fwhm_arcsec'], center, p['seeing_wave_um']))
    length = p['aperture']['length_arcsec'] or p['aperture']['length_fwhm'] * s_band
    n_spat = int(np.ceil(length / inst.platescale - 1e-9))
    if p['seeing_wave_um'] is None:
        f_slit, f_ap, f_peak = _fractions(p, inst, s_band, length)
    else:
        nodes = np.linspace(lo, hi, 7)          # FWHM varies by ~2% across a band
        fr = np.array([_fractions(p, inst, float(slitloss.seeing_at(p['seeing_fwhm_arcsec'], x, p['seeing_wave_um'])),
                                  length) for x in nodes])
        f_slit, f_ap, f_peak = (np.interp(wave, nodes, fr[:, k]) for k in range(3))

    # ---- detector (5.3.9)
    rn, w4 = inst.read_noise(p['readout']['mode'], p['readout']['n_reads'])
    warnings += [x for x in w4 if x not in warnings]
    dmeta = inst.detector()['meta']
    dark_rate, gain = float(dmeta['dark_e_per_s_per_pix']), float(dmeta['gain_e_per_adu'])
    limits = tuple(float(dmeta['linearity_adu'][k]) for k in ('nonlinear_1pct', 'nonlinear_5pct', 'saturated'))
    nf, nod = p['n_frames'], p['nod']
    s_rate = obj * f_ap * dlam                     # e-/s per spectral pixel in the aperture
    beta = b * n_spat
    d_rate, r2 = n_spat * dark_rate, n_spat * rn ** 2

    # ---- line window
    line_mask, line_window = None, None
    if p['spectrum']['shape'] == 'line':
        line = p['spectrum']['line']
        fwhm_obs = lsf.observed_line_fwhm(source.line_fwhm_A(line['wave_A'], line['fwhm_kms']), fwhm_A)
        if lo <= line['wave_A'] <= hi:
            line_mask = snr.line_window(wave, line['wave_A'], fwhm_obs)
            line_window = [line['wave_A'] - fwhm_obs / 2, line['wave_A'] + fwhm_obs / 2]
        else:
            warnings.append(f"spectrum.line.wave_A {line['wave_A']} is outside the {band} window "
                            f'({lo:.0f}-{hi:.0f} A); no line S/N')

    # ---- exposure time (N7)
    t = float(p['exptime_s'])
    if p['target_snr'] is not None:
        rho, ref = float(p['target_snr']), p['snr_reference']
        if ref == 'line' and line_mask is not None:
            k = int(line_mask.sum())
            t_sol = snr.solve_exptime(rho, s_rate[line_mask].sum(), beta[line_mask].sum(), d_rate * k, r2 * k, nf, nod)
        else:
            rho_pix = rho / np.sqrt(fwhm_pix) if ref == 'resel' else rho
            t_sol = snr.solve_exptime_median(rho_pix, s_rate, beta, d_rate, r2, nf, nod)
        if np.isfinite(t_sol):
            t = float(t_sol)
            if t < float(dmeta['min_integration_s']):
                warnings.append(f"solved exptime {t:.3g} s is below the minimum integration "
                                f"{dmeta['min_integration_s']} s; use fewer frames")
            elif t > 3600:
                warnings.append(f'solved exptime {t:.4g} s exceeds 3600 s; use more frames')
        else:
            warnings.append(f'target_snr {rho} is not reachable; exptime_s {t} used')

    # ---- signal, noise, S/N (5.3.7-5.3.10)
    S = s_rate * t
    B_ap = beta * t
    var1 = snr.frame_variance(S, B_ap, d_rate * t, r2, nod)
    snr_pix = snr.snr_pixel(S, var1, nf)
    snr_res = snr.snr_resel(snr_pix, fwhm_pix)
    snr_line = snr.line_snr(S * nf, var1 * nf, line_mask) if line_mask is not None else None

    # ---- saturation (5.3.11)
    sat = snr.saturation_peak(wave, obj, 1.0, 1.0, f_peak, dlam, t, b, dark_rate, gain, limits)
    if sat['flag'] != 'ok':
        warnings.append(PERSISTENCE_WARNING)

    out = {
        'meta': {'keck_etcs_version': keck_etcs.__version__, 'pypeit_version': th['pypeit_version'],
                 'calib_version': th['calib_version'], 'era': era.name, 'inputs': p},
        'wave_A': _tolist(wave),
        'dispersion_A_per_pix': float(dlam),
        'lsf_fwhm_A': float(fwhm_A),
        'resolving_power': _tolist(lsf.resolving_power(wave, fwhm_A)),
        'n_spec_per_resel': float(fwhm_pix),
        'slit_fraction': _tolist(f_slit),
        'aperture_fraction': _tolist(np.asarray(f_ap) / np.asarray(f_slit)),
        'n_spatial_pix': n_spat,
        'fwhm_arcsec_band': s_band,
        'throughput': _tolist(thru_pix),
        'atm_transmission': _tolist(atm_pix),
        'filter_transmission': _tolist(filt_pix),
        'signal_e': _tolist(S * nf),
        'sky_e': _tolist(B_ap * nf),
        'dark_e': float(d_rate * t * nf),
        'read_noise_e': float(np.sqrt(r2 * nf)),
        'noise_e': _tolist(np.sqrt(var1 * nf)),
        'snr_pixel': _tolist(snr_pix),
        'snr_resel': _tolist(snr_res),
        'summary': {'snr_pixel_median': float(np.median(snr_pix)), 'snr_resel_median': float(np.median(snr_res)),
                    'snr_line': snr_line, 'line_window_A': line_window,
                    'exptime_s': t, 'n_frames': nf, 'total_time_s': t * nf},
        'saturation': sat,
        'warnings': list(dict.fromkeys(warnings)),
    }
    return out
