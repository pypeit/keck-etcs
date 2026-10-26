---
file_format: mystnb
kernelspec:
  name: python3
  display_name: Python 3
---

# Examples

Every number and figure on this page is computed by `keck_etcs` while the
documentation is built (this page is a [MyST-NB](https://myst-nb.readthedocs.io)
notebook executed at build time), so it always reflects the version and
calibration in the banner above.

```{code-cell} python
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import keck_etcs
from keck_etcs.etc import compute

out = compute({})
print('keck_etcs', keck_etcs.__version__, '| calibration', out['meta']['calib_version'],
      '| latest era', out['meta']['era'])
```

## The example input files

The repository's `examples/*.json` are complete inputs; the same files work
with the command-line tool, `keck_etc examples/J_point.json --summary`.

```{code-cell} python
for f in sorted(Path('../examples').glob('*.json')):
    inp = json.loads(f.read_text())
    o = compute(inp)
    s = o['summary']
    line = f", line S/N {s['snr_line']:.2f}" if s.get('snr_line') is not None else ''
    print(f"{f.name:14s} {inp.get('band', 'J'):2s}: S/N per pixel {s['snr_pixel_median']:.3f}, "
          f"per resolution element {s['snr_resel_median']:.3f}{line}; "
          f"{s['n_frames']} x {s['exptime_s']:.0f} s; saturation {o['saturation']['flag']}; "
          f"{len(o['warnings'])} warning(s)")
```

## A J = 20 AB point source

The schema defaults: 0.7" slit and seeing, 4 x 120 s ABBA, MCDS-16, airmass
1.2, PWV 1.6 mm, the latest era.

```{code-cell} python
o = compute({'band': 'J', 'source': {'mag': 20.0, 'mag_system': 'AB'}})
print(f"snr_pixel_median = {o['summary']['snr_pixel_median']!r}")
print(f"snr_resel_median = {o['summary']['snr_resel_median']!r}")
print(f"slit fraction {o['slit_fraction']:.3f}, aperture fraction {o['aperture_fraction']:.3f}, "
      f"{o['n_spatial_pix']} spatial pixels, LSF {o['n_spec_per_resel']:.2f} pix")
for w in o['warnings']:
    print('warning:', w)

w = np.asarray(o['wave_A'])
fig, ax = plt.subplots(figsize=(9, 3.6))
ax.plot(w, o['snr_pixel'], 'k', lw=0.6, label='S/N per pixel')
ax.axhline(o['summary']['snr_pixel_median'], color='tab:orange', label='band median')
ax.set_xlabel('vacuum wavelength (A)')
ax.set_ylabel('S/N per pixel (4 frames)')
ax2 = ax.twinx()
ax2.semilogy(w, o['sky_e'], color='tab:blue', lw=0.4, alpha=0.6)
ax2.set_ylabel('sky electrons per pixel', color='tab:blue')
ax.legend(loc='upper left', fontsize=8)
fig.tight_layout()
```

## Exposure time against magnitude

`target_snr` solves for the exposure per frame at a fixed number of frames;
here S/N 5 per resolution element (band median) in 8 frames.

```{code-cell} python
mags = np.arange(18.0, 23.01, 0.5)
fig, ax = plt.subplots(figsize=(6, 3.6))
for band in ('J', 'J2'):
    t = [compute({'band': band, 'source': {'mag': float(m)}, 'n_frames': 8, 'target_snr': 5,
                  'snr_reference': 'resel'})['summary']['exptime_s'] for m in mags]
    ax.semilogy(mags, t, 'o-', label=band)
    print(band, ' '.join(f'{m:.1f}:{x:.0f}s' for m, x in zip(mags, t)))
ax.set_xlabel('magnitude (AB)')
ax.set_ylabel('exposure per frame (s)')
ax.grid(alpha=0.3)
ax.legend()
fig.tight_layout()
```

## An emission line

A line of 1e-17 erg/s/cm^2 at 12820 A with an intrinsic FWHM of 150 km/s,
no continuum; `snr_line` sums signal and variance within +- FWHM/2 of the
observed line.

```{code-cell} python
o = compute({'band': 'J', 'spectrum': {'shape': 'line',
             'line': {'wave_A': 12820.0, 'flux_cgs': 1e-17, 'fwhm_kms': 150}},
             'snr_reference': 'line'})
s = o['summary']
print(f"snr_line = {s['snr_line']:.3f} over {s['line_window_A'][0]:.1f}-{s['line_window_A'][1]:.1f} A "
      f"({s['n_frames']} x {s['exptime_s']:.0f} s)")
w = np.asarray(o['wave_A'])
sel = np.abs(w - 12820) < 40
fig, ax = plt.subplots(figsize=(6, 3.2))
ax.step(w[sel], np.asarray(o['signal_e'])[sel], where='mid', label='line electrons')
ax.step(w[sel], np.asarray(o['noise_e'])[sel], where='mid', label='noise electrons')
ax.axvspan(*s['line_window_A'], color='gold', alpha=0.3, label='line window')
ax.set_xlabel('vacuum wavelength (A)')
ax.legend(fontsize=8)
fig.tight_layout()
```

## Instrument eras

`throughput.date` selects the instrument era whose throughput is used; without
it the latest era applies. The same J = 20 AB source in each era:

```{code-cell} python
for date in ('2014-06-01', '2020-01-01', '2025-08-01', None):
    o = compute({'band': 'J', 'throughput': {'date': date}})
    print(f"date {str(date):10s} -> era {o['meta']['era']:18s} S/N per pixel {o['summary']['snr_pixel_median']:.3f}")
```
