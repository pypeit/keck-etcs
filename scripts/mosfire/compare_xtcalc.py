#!/usr/bin/env python
"""XTcalc sanity comparison (plan S12, design 6.2; results in reports/Keck_MOSFIRE_report_20261009.md, section 6).

Usage:
    conda run -n pypeit14b python scripts/mosfire/compare_xtcalc.py [--out DIR]

1. **XTcalc mode.** A line-by-line Python port of XTcalc v2.0 (Keck's XTcalc.tar, sha256 344b45b4...)
   (``XTcalc_dir/bin/XTcalc.pro``, G. Rudie 2012) on its own data files:
   the order-sorting filter (``mosfire/mosfire_<band>.txt``), the measured
   efficiency ``MosfireSpecEff/<band>eff.sm.dat`` x KMRef^2 (0.89 in J, 0.95
   in K), the May 2012 MOSFIRE sky ``MosfireSkySpec/<band>sky_cal_pA.sav``
   and the Gemini transmission ``Mauna_Kea_sky/mktrans_zm_16_10.sav`` (PWV
   1.6, airmass 1). Its constants: area 75 m^2, 0.18"/pix, RN 15/sqrt(N_reads)
   e-, dark 0.005, AB zero point 48.59, J 1.31 and K 2.10 A/pix, R = 3310 (J)
   or 3620 (K) x 0.7 / slit, every curve convolved in velocity space with a
   Gaussian of c/R on a 1 km/s grid (IDL ``interpol``, i.e. linear with
   linear extrapolation) and sampled on 3072 pixels centred on the band;
   the band is where the convolved filter exceeds 0.1; no slit loss; a
   two-point dither (x2 background variance) when N_exp > 1; ``theta``, the
   object's extent along the slit, sets the sky area (slit x theta) and the
   read-noise pixels (theta / 0.18).

   *XTcalc's band median.* In magnitude mode the S/N is the median over
   ``filt_index = NONzero_index``, which is computed on the full 3072-pixel
   grid but applied to the band-cut arrays; IDL clips out-of-range
   subscripts to the last element, so every index beyond the band repeats
   the band's last (red-edge) pixel. The port reproduces this and also
   reports the plain median over the band. Confirmed 2026-10-05: the XTcalc
   GUI at WMKO gave S/N 4.4 for J = 20 AB, 0.7"/0.7", 4 x 120 s, 16 reads
   (port: 4.437 with the quirk, 7.392 without).

2. **Check against the PDF.** The worked example of ``MOSFIRE_XTcalc.pdf``
   (Figure 1, GUI v1.8 beta): K band, 0.7" slit, theta 0.7", 1 exposure, 16
   Fowler reads, line flux 9e-18 erg/s/cm^2 at 6563 A, z = 2.3, source FWHM
   30 km/s, 1000 s, default airmass 1.0 and PWV 1.6; S/N 9.1 per observed
   FWHM (signal 1999.45, sky 46061.75, dark 58.92, read 12.87, total noise
   219.68 e- per FWHM; throughput 0.34).

3. **Table.** Flat f_nu, J = 17-23 AB, slits 0.7" and 1.0", 4 x 120 s
   MCDS-16 (two-point dither / ABBA), 0.7" seeing: XTcalc mode (theta =
   0.7", airmass 1, as its default) against ``keck_etcs.etc.compute``
   (airmass 1.2, PWV 1.6, default aperture, the 2017-02..2025-02
   throughput).

4. **Attribution.** One ingredient at a time, cumulatively, on the same S/N
   engine (XTcalc's noise formula, which is ours: S T + k (B T + n D T +
   n RN^2 N_exp)): XTcalc's band-median quirk; the constants (area 75 ->
   72.37 m^2, AB zero point 48.59 -> 48.6); the throughput (XTcalc 2012 ->
   our era curve x the Keck J filter); the atmosphere (airmass 1.0 -> 1.2);
   the sky model (MOSFIRE 2012 -> Gemini); the detector (RN 3.75 -> 5.8 e-,
   dark 0.005 -> 0.008); the extraction pixels (theta/0.18 = 3.89 -> ceil(1.5
   FWHM/0.1798) = 6); the slit and aperture loss (1 -> Moffat); the
   spectral sampling (1.31 A, velocity LSF at XTcalc's R, XTcalc's band ->
   1.2922 A, our LSF, the J half-power window). Steps 1-7 keep XTcalc's
   grid and LSF; the last uses ``compute``'s own arrays, and the residual
   to ``compute`` is the method difference (``compute`` convolves the
   product N0 T_atm T_sys).

Writes ``xtcalc_comparison.ecsv`` (table) and ``xtcalc_attribution.ecsv``
(the cumulative chain) to ``--out`` (default
``$KECK_ETCS_DATA/external/xtcalc/comparison/``) and prints both. Not a test.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from astropy.table import Table
from scipy.io import readsav

import keck_etcs
from keck_etcs import etc, paths
from keck_etcs.core import atmosphere, lsf
from keck_etcs.instruments.mosfire import MOSFIRE

H_ERG_S = 6.626068e-27
C_KMS = 2.99792458e5
HC_ERG_UM = H_ERG_S * 29979245800.0 * 1e4
AT_CM2, PIX, DET_RN, DARK, SLIT_W, NPIX, FNU_AB = 750000.0, 0.18, 15.0, 0.005, 0.7, 3072, 48.59
STAT = {'Y': {'disp': 1.05, 'lam': 1.05, 'rt': 3380.0, 'kmref': 0.85},    # XTcalc.pro Ystat, Jstat, Hstat, Kstat
        'J': {'disp': 1.31, 'lam': 1.25, 'rt': 3310.0, 'kmref': 0.89},
        'H': {'disp': 1.73, 'lam': 1.65, 'rt': 3660.0, 'kmref': 0.94},
        'K': {'disp': 2.10, 'lam': 2.2, 'rt': 3620.0, 'kmref': 0.95}}
PDF_EXAMPLE = {'S/N': 9.1, 'signal': 1999.45, 'background': 46061.75, 'dark': 58.92, 'RN': 12.87, 'noise': 219.68,
               'throughput': 0.34}
MAGS = np.arange(17.0, 23.01, 1.0)
SLITS = (0.7, 1.0)
NEXP, TFRAME, NREADS, SEEING = 4, 120.0, 16, 0.7


def xt_dir():
    return paths.data_root() / 'external' / 'xtcalc' / 'XTcalc_dir'


def interpol(x, xp, fp):
    """IDL ``interpol``: linear, with linear extrapolation beyond the ends; ``xp`` monotonic either way."""
    xp, fp = np.asarray(xp, float), np.asarray(fp, float)
    if xp[-1] < xp[0]:                    # the H and K filter files run red to blue
        xp, fp = xp[::-1], fp[::-1]
    y = np.interp(x, xp, fp)
    lo, hi = x < xp[0], x > xp[-1]
    y[lo] = fp[0] + (x[lo] - xp[0]) * (fp[1] - fp[0]) / (xp[1] - xp[0])
    y[hi] = fp[-1] + (x[hi] - xp[-1]) * (fp[-1] - fp[-2]) / (xp[-1] - xp[-2])
    return y


def mosfire_resolution(in_wave, in_flux, center, R, disp):
    """XTcalc's ``mosfire_resolution``: velocity-space Gaussian, sampled on its 3072-pixel grid (um)."""
    vel = np.arange(-100000.0, 100001.0)
    in_vel = (np.asarray(in_wave, float) / center - 1.0) * C_KMS
    sel = (in_vel > vel[0]) & (in_vel < vel[-1])
    f = interpol(vel, in_vel[sel], np.asarray(in_flux, float)[sel])
    sigma = (C_KMS / R) / (2 * np.sqrt(2 * np.log(2)))
    n = int(round(8 * sigma))
    n += (n % 2 == 0)
    kv = np.arange(n) - n // 2
    k = 1.0 / (np.sqrt(2 * np.pi) * sigma) * np.exp(-0.5 * kv ** 2 / sigma ** 2)
    conv = np.convolve(f, k, mode='same')
    conv[:n // 2] = 0.0                       # IDL convol leaves the edges at 0
    conv[-(n // 2):] = 0.0
    real = np.arange(NPIX) * disp * 1e-4
    real = real - real[int(round(NPIX / 2.0))] + center
    return real, interpol(real, center * (vel / C_KMS + 1.0), conv)


def xtcalc_inputs(band, slit, wvcol='16', airmass='10'):
    """XTcalc's spectra, convolved and band-cut (the arrays its S/N uses)."""
    st, x = STAT[band], xt_dir()
    R = st['rt'] * SLIT_W / slit
    fw, ft = np.loadtxt(x / 'mosfire' / f'mosfire_{band}.txt', comments='#', unpack=True)
    s = readsav(str(x / 'MosfireSkySpec' / f'{band}sky_cal_pA.sav'))
    lam = np.asarray(s['lam'], float) / 1e4
    mksky = np.clip(np.asarray(s['mksky'], float) / (0.7 * PIX * HC_ERG_UM) * lam * 1e5, 0, None)
    t = readsav(str(x / 'Mauna_Kea_sky' / f'mktrans_zm_{wvcol}_{airmass}.sav'))
    tw, tp = np.loadtxt(x / 'MosfireSpecEff' / f'{band}eff.sm.dat', unpack=True)
    tp = np.clip(tp, 0, None) * st['kmref'] ** 2
    grid, flt = mosfire_resolution(fw, ft, st['lam'], R, st['disp'])
    band_idx = np.flatnonzero(flt > 0.1)
    _, tran = mosfire_resolution(np.asarray(t['tran_lam'], float), np.asarray(t['trans'], float), st['lam'], R, st['disp'])
    _, tpo = mosfire_resolution(tw / 1e4, tp, st['lam'], R, st['disp'])
    _, bk = mosfire_resolution(lam, mksky, st['lam'], R, st['disp'])
    nonzero = np.flatnonzero((bk >= 0) & (bk != 0))
    bk = np.clip(bk, 0, None)
    return {'R': R, 'disp': st['disp'], 'center': st['lam'], 'grid_um': grid[band_idx], 'tran': tran[band_idx],
            'tp': tpo[band_idx], 'bk': bk[band_idx], 'nonzero_full': nonzero, 'n_band': band_idx.size,
            'raw': {'filter': (fw, ft), 'sky': (lam, mksky), 'trans': (np.asarray(t['tran_lam'], float),
                                                                       np.asarray(t['trans'], float)), 'tp': (tw / 1e4, tp)}}


def quirk_index(inp):
    """XTcalc's ``filt_index``: full-grid indices, clipped by IDL to the band-cut arrays."""
    return np.clip(inp['nonzero_full'], 0, inp['n_band'] - 1)


def engine(wave_A, dlam, T_tot, T_atm, B, idx, mag, area_m2, slit, n_spat, p, rn, dark, f_ap, nexp, t_frame,
           ab_zp=FNU_AB):
    """Median S/N per pixel over ``idx`` (XTcalc's and our noise formula; see the module docstring)."""
    fnu = 10 ** (-0.4 * (mag + ab_zp))
    S = fnu / (H_ERG_S * wave_A) * area_m2 * 1e4 * T_atm * T_tot * f_ap * dlam
    Bp = B / 10.0 * area_m2 * T_tot * slit * (n_spat * p) * dlam
    T = nexp * t_frame
    k = 2.0 if nexp > 1 else 1.0
    snr = S * T / np.sqrt(S * T + k * ((Bp + dark * n_spat) * T + rn ** 2 * n_spat * nexp))
    return float(np.median(snr[idx]))


def xtcalc_line(band, slit, theta, nreads, nexp, time, lineF, line_um, fwhm_kms):
    """XTcalc line mode; the values of its output table."""
    inp = xtcalc_inputs(band, slit)
    st = STAT[band]
    center, R, disp = line_um, inp['R'], inp['disp']
    res = center / R
    width = np.hypot(center * fwhm_kms / C_KMS, res)
    w = inp['grid_um']
    idx = np.flatnonzero(np.abs(w - center) <= 0.5 * width)
    bk = inp['bk'] * inp['tp'] * slit * theta * (AT_CM2 * 1e-4) * (disp / 10.0)
    signal_atm = lineF * 1e-18 / HC_ERG_UM * center * AT_CM2
    sigma = width / (2 * np.sqrt(2 * np.log(2)))
    sig = signal_atm / (np.sqrt(2 * np.pi) * sigma) * np.exp(-0.5 * (w - center) ** 2 / sigma ** 2) * disp / 1e4
    sig = sig * inp['tp'] * inp['tran']
    npix_spec = width * 1e4 / disp
    npix_spat = theta / PIX
    dither = 2.0 if nexp > 1 else 1.0
    noise = np.sqrt(sig * time + dither * ((bk + DARK * npix_spat) * time + DET_RN ** 2 / nreads * npix_spat * nexp))
    sn = sig * time / noise
    return {'S/N': float(np.mean(np.sqrt(npix_spec) * sn[idx])),
            'signal': float(np.mean(sig[idx]) * npix_spec * time),
            'background': float(np.mean(bk[idx]) * npix_spec * time),
            'dark': DARK * npix_spec * npix_spat * time,
            'RN': DET_RN / np.sqrt(nreads) * np.sqrt(npix_spec * npix_spat) * np.sqrt(nexp),
            'noise': float(np.mean(noise[idx]) * np.sqrt(npix_spec)),
            'throughput': float(np.mean(inp['tp'][idx])), 'resolution_A': res * 1e4, 'n_pix_line': int(idx.size)}


def ours_raw():
    """Our raw ingredients: filter-free era throughput x Keck J filter; Gemini T_atm and sky at X 1.2, PWV 1.6."""
    era = MOSFIRE.era_for_date('2022-04-09')[0]
    th = MOSFIRE.throughput(era)
    f = MOSFIRE.filter_curve('J')
    tp = np.interp(f['wave_A'], th['wave_A'], th['thru']) * f['transmission']
    g = MOSFIRE.sky_grid()
    tr, _ = atmosphere.interp_grid(g['trans'], g['airmass'], g['pwv_mm'], 1.2, 1.6)
    sky, _ = atmosphere.interp_grid(g['skybg'], g['airmass'], g['pwv_mm'], 1.2, 1.6)
    return {'tp': (f['wave_A'] / 1e4, tp), 'trans': (g['wave_A'] / 1e4, np.clip(tr, 0, 1)),
            'sky': (g['wave_A'] / 1e4, np.clip(sky, 0, None))}


def ours_inputs(slit, mag):
    inp = {'band': 'J', 'slit_width_arcsec': slit, 'source': {'type': 'point', 'mag': float(mag), 'mag_system': 'AB'},
           'seeing_fwhm_arcsec': SEEING, 'exptime_s': TFRAME, 'n_frames': NEXP,
           'readout': {'mode': 'MCDS', 'n_reads': NREADS}, 'nod': 'ABBA', 'airmass': 1.2, 'pwv_mm': 1.6,
           'throughput': {'date': '2022-04-09'}}
    return inp


def chain(slit, mags, ours):
    """The cumulative attribution chain for one slit; one dict per magnitude."""
    xi = xtcalc_inputs('J', slit)
    R, disp, center = xi['R'], xi['disp'], xi['center']
    wave_A = xi['grid_um'] * 1e4
    conv = lambda raw: mosfire_resolution(raw[0], raw[1], center, R, disp)[1][np.flatnonzero(
        mosfire_resolution(*xi['raw']['filter'], center, R, disp)[1] > 0.1)]
    tp_o, tr_o1, tr_o, sky_o = conv(ours['tp']), None, conv(ours['trans']), conv(ours['sky'])
    g = MOSFIRE.sky_grid()
    tr10, _ = atmosphere.interp_grid(g['trans'], g['airmass'], g['pwv_mm'], 1.0, 1.6)
    tr_o1 = conv((g['wave_A'] / 1e4, np.clip(tr10, 0, 1)))
    theta = SEEING
    plain = np.arange(xi['n_band'])
    q = quirk_index(xi)
    rows = []
    for mag in mags:
        o = etc.compute(ours_inputs(slit, mag))
        f_ap = o['slit_fraction'] * o['aperture_fraction']
        n_o, p_o = o['n_spatial_pix'], MOSFIRE.platescale
        rn_o = MOSFIRE.read_noise('MCDS', NREADS)[0]
        d_o = float(MOSFIRE.detector()['meta']['dark_e_per_s_per_pix'])
        base = dict(dlam=disp, slit=slit, nexp=NEXP, t_frame=TFRAME)
        cfg = dict(T_tot=xi['tp'], T_atm=xi['tran'], B=xi['bk'], area_m2=75.0, ab_zp=FNU_AB, n_spat=theta / PIX,
                   p=PIX, rn=DET_RN / np.sqrt(NREADS), dark=DARK, f_ap=1.0)
        steps = []

        def run(label, idx, **chg):
            cfg.update(chg)
            steps.append((label, engine(wave_A, idx=idx, mag=mag, **base, **cfg)))

        run('XTcalc as coded (band-median quirk)', q)
        run('band median without the quirk', plain)
        run('area 75 -> 72.37 m^2, AB zp 48.59 -> 48.6', plain, area_m2=MOSFIRE.area_m2, ab_zp=48.6)
        run('throughput: XTcalc 2012 -> our era curve x J filter', plain, T_tot=tp_o)
        run('atmosphere: XTcalc airmass 1.0 -> Gemini grid at 1.0', plain, T_atm=tr_o1)
        run('atmosphere: airmass 1.0 -> 1.2', plain, T_atm=tr_o)
        run('sky: MOSFIRE 2012 -> Gemini (X 1.2, PWV 1.6)', plain, B=sky_o)
        run(f'detector: RN 3.75 -> {rn_o:.1f} e-, dark 0.005 -> {d_o}', plain, rn=rn_o, dark=d_o)
        run(f'extraction: theta/0.18 = {theta / PIX:.2f} -> {n_o} pix of 0.1798"', plain, n_spat=n_o, p=p_o)
        run(f'slit x aperture loss 1 -> {f_ap:.3f}', plain, f_ap=f_ap)
        # spectral sampling: compute's own arrays on its grid and window
        w = np.array(o['wave_A'])
        T_tot, T_atm = np.array(o['throughput']), np.array(o['atm_transmission'])
        b = np.array(o['sky_e']) / (NEXP * TFRAME * n_o)
        B = np.where(T_tot > 0, 10.0 * b / (MOSFIRE.area_m2 * np.where(T_tot > 0, T_tot, 1) * slit * p_o *
                                              o['dispersion_A_per_pix']), 0.0)
        steps.append((f'sampling: {disp} A, R {R:.0f} (velocity), XTcalc band -> {o["dispersion_A_per_pix"]:.4f} A, '
                      f'LSF {o["lsf_fwhm_A"]:.2f} A, J half-power window',
                      engine(w, o['dispersion_A_per_pix'], T_tot, T_atm, B, np.arange(w.size), mag, MOSFIRE.area_m2,
                             slit, n_o, p_o, rn_o, d_o, f_ap, NEXP, TFRAME, ab_zp=48.6)))
        steps.append(('keck_etcs compute (convolves N0 T_atm T_sys)', o['summary']['snr_pixel_median']))
        rows.append({'mag': mag, 'steps': steps})
    return rows


def main(out=None):
    out = Path(out) if out else paths.data_root() / 'external' / 'xtcalc' / 'comparison'
    out.mkdir(parents=True, exist_ok=True)
    # 2. the PDF example
    ex = xtcalc_line('K', 0.7, 0.7, 16, 1, 1000.0, 9.0, 0.6563 * 3.3, 30.0)
    print('PDF example (K, 0.7" slit, theta 0.7", 1 x 1000 s, 16 reads, 9e-18 at 6563 A, z 2.3, 30 km/s):')
    for k in PDF_EXAMPLE:
        print(f'  {k:11s} port {ex[k]:10.2f}   PDF (GUI v1.8) {PDF_EXAMPLE[k]:10.2f}   ratio {ex[k] / PDF_EXAMPLE[k]:.3f}')
    print(f"  resolution {ex['resolution_A']:.2f} A (PDF 6.0); {ex['n_pix_line']} pixels in the line FWHM")
    ok_pdf = abs(ex['S/N'] / PDF_EXAMPLE['S/N'] - 1) <= 0.10
    print(f"  S/N within 10 percent of the PDF: {'PASS' if ok_pdf else 'FAIL'}")

    # 3-4. table and attribution
    ours = ours_raw()
    tab, att = [], []
    for slit in SLITS:
        for r in chain(slit, MAGS, ours):
            st = r['steps']
            tab.append({'slit_arcsec': slit, 'mag_ab': r['mag'], 'snr_xtcalc': st[0][1], 'snr_xtcalc_plain_median': st[1][1],
                        'snr_keck_etcs': st[-1][1], 'ratio_ours_over_xtcalc': st[-1][1] / st[0][1]})
            for i, (label, v) in enumerate(st):
                att.append({'slit_arcsec': slit, 'mag_ab': r['mag'], 'step': i, 'change': label, 'snr': v,
                            'factor': v / st[i - 1][1] if i else 1.0})
    t, a = Table(rows=tab), Table(rows=att)
    meta = {'script': 'scripts/mosfire/compare_xtcalc.py', 'keck_etcs_version': keck_etcs.__version__,
            'calib_version': MOSFIRE.throughput(MOSFIRE.eras[1])['calib_version'],
            'case': f'flat f_nu J, {NEXP} x {TFRAME:.0f} s MCDS-{NREADS} ABBA, seeing {SEEING}"; XTcalc theta {SEEING}", '
                    'airmass 1.0 (its default); ours airmass 1.2, PWV 1.6',
            'xtcalc': 'XTcalc v2.0 (Keck XTcalc.tar) data files, ported to Python',
            'pdf_example': {'port': ex, 'pdf': PDF_EXAMPLE, 'within_10pct': bool(ok_pdf)}}
    t.meta, a.meta = dict(meta), dict(meta)
    for c in ('snr_xtcalc', 'snr_xtcalc_plain_median', 'snr_keck_etcs', 'ratio_ours_over_xtcalc'):
        t[c].format = '.3f'
    a['snr'].format = a['factor'].format = '.3f'
    t.write(out / 'xtcalc_comparison.ecsv', format='ascii.ecsv', overwrite=True)
    a.write(out / 'xtcalc_attribution.ecsv', format='ascii.ecsv', overwrite=True)
    print('\nS/N per pixel, band median (XTcalc mode vs keck_etcs):')
    t.pprint(max_lines=-1, max_width=-1)
    for slit in SLITS:
        print(f'\nattribution, {slit}" slit (cumulative S/N; factor = this step / previous):')
        labels = [x['change'] for x in att if x['slit_arcsec'] == slit and x['mag_ab'] == MAGS[0]]
        hdr = ''.join(f'  J={m:.0f}: S/N  factor' for m in MAGS[::3])
        print(f"{'step':66s}{hdr}")
        for i, lab in enumerate(labels):
            cells = ''
            for m in MAGS[::3]:
                r = [x for x in att if x['slit_arcsec'] == slit and x['mag_ab'] == m and x['step'] == i][0]
                cells += f"  {r['snr']:9.3f} {r['factor']:6.3f}"
            print(f'{i:2d} {lab[:63]:63s}{cells}')
    print(f'\nwrote {out}/xtcalc_comparison.ecsv and xtcalc_attribution.ecsv')
    return t, a, ex


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--out', help='output directory')
    main(p.parse_args().out)
    sys.exit(0)
