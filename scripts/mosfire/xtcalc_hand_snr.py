#!/usr/bin/env python
"""XTcalc's band-median S/N for one case, by hand from its formula, against ``compute`` (plan S9 check).

Usage:
    conda run -n pypeit14b python scripts/mosfire/xtcalc_hand_snr.py [--mag 20] [--theta 0.7]

Re-implements the magnitude mode of XTcalc v2.3 (``XTcalc_dir/bin/XTcalc.pro``)
on XTcalc's own data files, for the S9 verification case: J = 20 AB flat
f_nu, 0.7" slit, 0.7" seeing, 4 x 120 s MCDS-16 ABBA, airmass 1.2, PWV 1.6
mm. XTcalc, from its source:

- constants: area 75 m^2 (``AT = 750000`` cm^2), 0.18"/pix, RN 15 e- CDS
  scaled as 15/sqrt(N_reads), dark 0.005 e-/s/pix, J dispersion 1.31 A/pix,
  R = 3310 x 0.7 / slit;
- throughput ``MosfireSpecEff/Jeff.sm.dat x 0.89^2`` (negative values set
  to 0); atmosphere ``Mauna_Kea_sky/mktrans_zm_<pwv>_<airmass>.sav``, only
  airmass 1.0/1.5/2.0 (both bracketing grids are shown); sky the May 2012
  MOSFIRE spectrum ``MosfireSkySpec/Jsky_cal_pA.sav`` converted to
  photons/s/arcsec^2/nm/m^2;
- every curve convolved with a Gaussian of R and sampled at 1.31 A pixels;
- per spectral pixel and second: signal ``f_nu/h * AT / lam * T_atm * tp *
  disp`` (no slit loss: "object assumed <= slit"), sky ``B * tp * slit *
  theta * AT[m^2] * disp[nm]``, with ``theta`` the object's extent along the
  slit and ``theta / 0.18`` spatial pixels;
- noise^2 = S t + 2 (B t + dark (theta/0.18) t + RN^2/N_reads (theta/0.18)
  N_exp), the factor 2 for N_exp > 1 (two dither positions), t the total
  time; S/N per pixel = median over the pixels where the convolved filter
  exceeds 0.1 and the sky is >= 0.

The full comparison over a grid of magnitudes and slits is S12
(``scripts/mosfire/compare_xtcalc.py``, part 4).
"""
import argparse
import sys

import numpy as np
from scipy.io import readsav

from keck_etcs import etc, paths

H_ERG_S = 6.626068e-27
C_UM_S = 2.99792458e14


def gauss_convolve(wave_um, flux, R, center_um, out_wave):
    """Gaussian of FWHM center/R (constant in velocity, as XTcalc), sampled at out_wave."""
    grid = np.arange(wave_um.min(), wave_um.max(), center_um / R / 20.0)
    f = np.interp(grid, wave_um, flux)
    sigma = center_um / R / (2 * np.sqrt(2 * np.log(2))) / (grid[1] - grid[0])
    half = int(np.ceil(5 * sigma))
    k = np.exp(-0.5 * (np.arange(-half, half + 1) / sigma) ** 2)
    k /= k.sum()
    return np.interp(out_wave, grid, np.convolve(f, k, mode='same'))


def xtcalc(mag_ab=20.0, slit=0.7, theta=0.7, nreads=16, nexp=4, texp=120.0, airmass='10', wvcol='16'):
    x = paths.data_root() / 'external' / 'xtcalc' / 'XTcalc_dir'
    AT, pix_scale, det_rn, dark, disp, R = 750000.0, 0.18, 15.0, 0.005, 1.31, 3310.0 * 0.7 / slit
    center = 1.25
    dither = 2.0 if nexp > 1 else 1.0
    # data
    tw, tp = np.loadtxt(x / 'MosfireSpecEff' / 'Jeff.sm.dat', unpack=True)
    tw, tp = tw / 1e4, np.clip(tp, 0, None) * 0.89 ** 2
    s = readsav(str(x / 'MosfireSkySpec' / 'Jsky_cal_pA.sav'))
    lam = np.asarray(s['lam'], float) / 1e4
    hc_erg_um = H_ERG_S * C_UM_S
    mksky = np.clip(np.asarray(s['mksky'], float) / (0.7 * pix_scale * hc_erg_um) * lam * 1e5, 0, None)
    t = readsav(str(x / 'Mauna_Kea_sky' / f'mktrans_zm_{wvcol}_{airmass}.sav'))
    trl, tr = np.asarray(t['tran_lam'], float), np.asarray(t['trans'], float)
    fw, ft = np.loadtxt(x / 'mosfire' / 'mosfire_J.txt', unpack=True, comments='#')
    # pixel grid: 3072 pixels of disp centred on 1.25 um
    npix = 3072
    wave = (np.arange(npix) - round(npix / 2)) * disp * 1e-4 + center
    filt = gauss_convolve(fw, ft, R, center, wave)
    band = filt > 0.1
    T = gauss_convolve(trl, tr, R, center, wave)[band]
    TP = gauss_convolve(tw, tp, R, center, wave)[band]
    B = gauss_convolve(lam, mksky, R, center, wave)[band]
    B = np.clip(B, 0, None)
    w = wave[band]
    sn_idx = B >= 0
    sig = 10 ** (-0.4 * (mag_ab + 48.59)) / H_ERG_S * AT / w * T * TP * (disp / 1e4)      # e-/s/pix
    bk = B * TP * slit * theta * (AT * 1e-4) * (disp / 10.0)
    npx = theta / pix_scale
    time = texp * nexp
    noise = np.sqrt(sig * time + dither * ((bk + dark * npx) * time + det_rn ** 2 / nreads * npx * nexp))
    snr = sig * time / noise
    return {'snr_pixel_median': float(np.median(snr[sn_idx])), 'n_pix': int(sn_idx.sum()),
            'wave_um': (float(w[0]), float(w[-1])), 'signal_med': float(np.median(sig[sn_idx]) * time),
            'sky_med': float(np.median(bk[sn_idx]) * time), 'tp_med': float(np.median(TP)),
            'rn_e': det_rn / np.sqrt(nreads), 'n_spatial': npx}


def main(mag=20.0, theta=0.7):
    inp = {'band': 'J', 'slit_width_arcsec': 0.7, 'source': {'type': 'point', 'mag': mag, 'mag_system': 'AB'},
           'seeing_fwhm_arcsec': 0.7, 'exptime_s': 120, 'n_frames': 4,
           'readout': {'mode': 'MCDS', 'n_reads': 16}, 'nod': 'ABBA', 'airmass': 1.2, 'pwv_mm': 1.6}
    ours = etc.compute(inp)
    s = ours['summary']
    f_ap = ours['slit_fraction'] * ours['aperture_fraction']
    print(f'case: J = {mag} AB flat f_nu, 0.7" slit, 0.7" seeing, 4 x 120 s MCDS-16 ABBA, X 1.2, PWV 1.6')
    print(f"keck_etcs ({ours['meta']['calib_version']}): band-median S/N per pixel {s['snr_pixel_median']:.3f} "
          f"(window {ours['wave_A'][0]:.0f}-{ours['wave_A'][-1]:.0f} A; f_slit x f_ap {f_ap:.3f}; "
          f"{ours['n_spatial_pix']} spatial pix; RN 5.8 e-; area 72.37 m^2)")
    for am in ('10', '15'):
        for th in sorted({theta, 1.05}):
            r = xtcalc(mag, theta=th, airmass=am)
            print(f"XTcalc by hand, airmass {int(am) / 10:.1f}, theta {th}\": S/N per pixel {r['snr_pixel_median']:.3f} "
                  f"(ratio ours/XTcalc {s['snr_pixel_median'] / r['snr_pixel_median']:.3f}; {r['n_pix']} pix "
                  f"{r['wave_um'][0]:.4f}-{r['wave_um'][1]:.4f} um; median throughput {r['tp_med']:.3f}; "
                  f"{r['n_spatial']:.2f} spatial pix; RN {r['rn_e']:.2f} e-)")
    # the leading difference: XTcalc has no slit loss
    print(f'without our slit and aperture loss ({f_ap:.3f}) the source term alone would rise by {1 / f_ap:.2f}x')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--mag', type=float, default=20.0)
    p.add_argument('--theta', type=float, default=0.7, help='XTcalc object extent along the slit [arcsec]')
    a = p.parse_args()
    sys.exit(main(a.mag, a.theta))
