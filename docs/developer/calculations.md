# How the calculations are performed

This page is the developer's walk through the two calculation chains of
`keck_etcs`, with the equations as the code implements them and the PypeIt
routines they rest on:

1. the **calibration chain**, from a standard star's raw frames to the
   per-era throughput curve that ships in `keck_etcs/data/`;
2. the **ETC chain**, {func}`keck_etcs.etc.compute`, from a JSON input to
   signal, noise, S/N, exposure time and saturation.

The design document ([Keck/MOSFIRE design](../keck_mosfire_design.md),
sections 4 and 5) records *why* each choice was made (the D and N
decisions quoted below); this page records *what is computed* and *where*.
The [Python API](../api/index.md) pages hold the docstrings.

## Notation

| Symbol | Meaning | Value or source |
|---|---|---|
| $\lambda$ | wavelength, vacuum | Å (N5) |
| $\Delta\lambda$ | dispersion | 1.2922 Å/pix for J, J2 (`instruments/mosfire.py`) |
| $A$ | Keck effective collecting area | 72.3674 m² = 7.23674e5 cm², PypeIt `KeckTelescopePar` (N1) |
| $h c$ | Planck constant times speed of light | 1.98645e-8 erg Å |
| $p$ | spatial plate scale | 0.1798 "/pix, PypeIt `keck_mosfire` |
| $w$ | slit width | input, arcsec |
| $s$ | seeing FWHM at the band | input, arcsec |
| $L$ | extraction-aperture length along the slit | `aperture.length_fwhm` × $s$ or `aperture.length_arcsec` |
| $t$ | exposure time per frame | s |
| $N_f$ | number of frames | |
| $X$ | airmass | |
| $N_\lambda$ | detected photon (electron) rate per Å | e⁻/s/Å |
| $F_\lambda$ | flux density | erg/s/cm²/Å |
| $T_{\rm atm}$, $T_{\rm sys}$ | atmospheric and system transmission | 0 to 1 |

## 1. Calibration chain: from a standard star to the throughput curve

### 1.1 Reduction with PypeIt

Each standard-star night is reduced by PypeIt inside a Nautilus pod
(`nautilus/README.md`), driven by `scripts/mosfire/reduce_standard.py`:

- `pypeit_setup` on the night's raw frames, then a patched PypeIt file
  (frame types from the dome-lamp and telescope cards, nod pairs through
  `comb_id`/`bkg_id`, the parameter block of
  `keck_etcs/data/pypeit_par/`), then `run_pypeit`. This yields one
  `spec1d` file per standard frame, in counts, with the spatial FWHM of the
  extracted object.
- `scripts/mosfire/build_sensfunc.py`: `pypeit_coadd_1dspec` of the
  standard's frames in counts (`flux_value = False`), then
  `pypeit_sensfunc` with the `IR` algorithm and the settings of
  `keck_etcs/data/pypeit_par/keck_mosfire_J.sens` (design 4.3):
  `polyorder = 6`, `tell_npca = 3`, telluric grid
  `TellPCA_3000_26000_R10000.fits`, no extrapolation.

PypeIt does the following with that call.

| Step | PypeIt code |
|---|---|
| Driver of the `IR` algorithm | [`pypeit.sensfunc.IRSensFunc.compute_zeropoint`](https://github.com/pypeit/PypeIt/blob/bc18a3ba46d1d331da0875424c63999e578a4937/pypeit/sensfunc.py) |
| Joint fit of zero-point polynomial and telluric model | [`pypeit.core.telluric.sensfunc_telluric`](https://github.com/pypeit/PypeIt/blob/bc18a3ba46d1d331da0875424c63999e578a4937/pypeit/core/telluric.py) |
| Telluric model evaluation (PCA coefficients, resolution, shift, stretch) | [`pypeit.core.telluric.eval_telluric`](https://github.com/pypeit/PypeIt/blob/bc18a3ba46d1d331da0875424c63999e578a4937/pypeit/core/telluric.py) |
| Zero point from counts and the standard's flux | [`pypeit.core.flux_calib.compute_zeropoint`](https://github.com/pypeit/PypeIt/blob/bc18a3ba46d1d331da0875424c63999e578a4937/pypeit/core/flux_calib.py) |
| Zero point unit constant | [`pypeit.core.flux_calib.zp_unit_const`](https://github.com/pypeit/PypeIt/blob/bc18a3ba46d1d331da0875424c63999e578a4937/pypeit/core/flux_calib.py) |
| Zero point to throughput | [`pypeit.core.flux_calib.zeropoint_to_throughput`](https://github.com/pypeit/PypeIt/blob/bc18a3ba46d1d331da0875424c63999e578a4937/pypeit/core/flux_calib.py) |
| MOSFIRE band trims and Paschen-line masks on the standard | [`pypeit.spectrographs.keck_mosfire.KeckMOSFIRESpectrograph.tweak_standard`](https://github.com/pypeit/PypeIt/blob/bc18a3ba46d1d331da0875424c63999e578a4937/pypeit/spectrographs/keck_mosfire.py) |
| Standard-star spectra (CALSPEC and the other archives, by position) | [`pypeit.core.standard.get_standard_spectrum`](https://github.com/pypeit/PypeIt/blob/bc18a3ba46d1d331da0875424c63999e578a4937/pypeit/core/standard.py) |
| Vega model for A0V stars | [`pypeit.core.standard.VegaStandard`](https://github.com/pypeit/PypeIt/blob/bc18a3ba46d1d331da0875424c63999e578a4937/pypeit/core/standard.py) |
| Telescope area, plate scale, gain, dark, read noise | [`pypeit.telescopes.KeckTelescopePar`](https://github.com/pypeit/PypeIt/blob/bc18a3ba46d1d331da0875424c63999e578a4937/pypeit/telescopes.py), [`pypeit.spectrographs.keck_mosfire`](https://github.com/pypeit/PypeIt/blob/bc18a3ba46d1d331da0875424c63999e578a4937/pypeit/spectrographs/keck_mosfire.py) |

The links point at the commit the calibration release was reduced with
(`nautilus/pypeit_pin.txt`); the same objects are described in the
[PypeIt API documentation](https://pypeit.readthedocs.io/en/latest/api/pypeit.core.flux_calib.html).

### 1.2 PypeIt's zero point

PypeIt's sensitivity function is a *spectroscopic zero point*. From the
counts of the standard, $C(\lambda)$, in a frame of exposure time $t$,

$$
N_\lambda(\lambda) = \frac{C(\lambda)}{t\,\Delta\lambda} \quad [\mathrm{e^-/s/\mathring{A}}],
$$

and with the true flux density of the standard $F_{\lambda,\star}$ and the
fitted telluric transmission $T_{\rm tell}(\lambda)$ at the observed airmass,
`compute_zeropoint` evaluates

$$
\mathrm{ZP}(\lambda) = -2.5 \log_{10}\!\left[ \frac{\lambda^2}{c}\,
\frac{T_{\rm tell}(\lambda)\, F_{\lambda,\star}(\lambda)}{N_\lambda(\lambda)} \Big/ 3631\ \mathrm{Jy} \right] ,
$$

which is the **AB magnitude of a source that produces 1 e⁻/s/Å** at the
detector, after the telluric absorption is divided out (D7). In the code
the bracket is written as `S_nu_dimless = wave**2 * tellmodel * flam_std /
N_lam` with $F_\lambda$ in units of $10^{-17}$ erg/s/cm²/Å, plus the constant
`ZP_UNIT_CONST` = 40.0921 that carries the $1/c$, the unit of $F_\lambda$ and
the 3631 Jy. The `IR` algorithm does not take this ratio pixel by pixel:
`sensfunc_telluric` fits a polynomial in $\lambda$ of order `polyorder` for
$\mathrm{ZP}(\lambda)$ **jointly** with the telluric model (three PCA
coefficients, a resolution, a shift and a stretch; `tell_npca = 3`, design
4.3) by differential evolution, and the `SensFunc` file stores the fitted
`zeropoint` on its `wave` grid together with the `Telluric` model
(`TELL_THETA`). `tweak_standard` zeroes the J2 spectrum outside
1.117-1.260 µm and masks the Paschen lines first.

Standard-star spectra. White dwarfs and the other archive standards come
from PypeIt's archives by position (`get_standard_spectrum`; CALSPEC for
LDS749B, GD153, Feige 110). A0V telluric stars (D2, N3) have no measured
spectrum, so {mod}`keck_etcs.calib.standards` passes PypeIt
`star_type = A0`, `star_mag = V_eq`, which makes PypeIt use
`VegaStandard(V_eq)` = Vega × $10^{0.4(0.03 - V_{\rm eq})}$, with

$$
V_{\rm eq} = 0.03 + J_{2\mathrm{MASS}} - J_{\rm synth}(\mathrm{Vega}),
\qquad
J_{\rm synth} = -2.5\log_{10}\frac{\int F_\lambda R_J \lambda\, d\lambda}{\int F_0 R_J \lambda\, d\lambda},
$$

$R_J$ being PypeIt's `TMASS-J` response and $F_0$ = 3.129e-10 erg/s/cm²/Å
the Cohen et al. (2003) zero point, so the model's synthetic 2MASS J equals
the star's catalogue J ({func}`keck_etcs.calib.standards.v_equivalent`,
{func}`keck_etcs.calib.standards.synthetic_tmass_j`).

### 1.3 Zero point to end-to-end throughput

The throughput is the fraction of the photons arriving above the atmosphere
that become electrons. A source at AB magnitude $\mathrm{ZP}$ has
$f_\nu = 10^{-0.4(\mathrm{ZP} + 48.6)}$ erg/s/cm²/Hz, hence a photon rate per
Å above the atmosphere of $f_\nu A / (h\lambda)$; it yields 1 e⁻/s/Å, so

$$
T_{\rm sys}(\lambda) = \frac{h\,\lambda\,10^{\,0.4\,(\mathrm{ZP}(\lambda) + 48.6)}}{A}
\qquad (\lambda\ \mathrm{in\ cm},\ A = 7.23674\times10^{5}\ \mathrm{cm^2}).
$$

This is PypeIt's `zeropoint_to_throughput(wave, zeropoint, eff_aperture)`,
which {func}`keck_etcs.calib.harvest.zeropoint_to_throughput` calls with
the Keck area (N1); `harvest` never re-implements it, so a change in PypeIt
would show up here. {func}`keck_etcs.calib.harvest.throughput_curve` then

- interpolates the fitted zero point onto the common 1 Å vacuum grid
  (9000 + k Å) over the range where the fit is positive and finite;
- computes `thru_raw` = $T_{\rm sys}$ including the filter;
- divides by the band's filter curve where it exceeds 0.05 to give `thru`,
  the **filter-free** throughput (telescope + spectrograph + detector; D5),
  so that J, J2 and J3 standards can be combined and the ETC re-applies the
  filter of the band it is asked about.

The per-standard row (`harvest.ROW_COLUMNS`, one line of `standards.ecsv`) also
records `zp_1200`, `zp_1250`, `zp_1300` (masked where the fit does not
reach), the band medians `thru_median_1117_1260` and
`thru_median_1117_1250`, the median PypeIt spatial FWHM, the airmass, the
readout mode and the reduction provenance (image, digest, PypeIt commit).

**Precipitable water vapour.** The PCA telluric model has no PWV
parameter, so {func}`keck_etcs.calib.harvest.estimate_pwv` takes the
fitted transmission $T_{\rm tell}$ and finds the PWV at which the Gemini
transmission grid (the one the ETC uses, section 2.4), interpolated to the
standard's airmass and smoothed to the fitted resolution, minimises
$\sum (T_{\rm Gemini} - T_{\rm tell})^2$ over 1.117-1.260 µm on a
logarithmic search from 0.5 to 10 mm. It is a diagnostic (trend analysis,
design 4.6), not a correction.

### 1.4 Combining standards into an era curve

{func}`keck_etcs.calib.combine.combine_era` builds
`keck_etcs/data/mosfire/throughput/mosfire_thru_<era>.ecsv` for each
instrument era (D6; `instruments/mosfire.py` `ERAS`) from the committed
per-standard curves:

1. each row's filter-free curve is kept inside its filter's half-power
   band; J rows only where the J filter is at least 0.9 of its peak
   (`EDGE_TRIM_FRAC`), A0V rows only redward of 11900 Å (`A0V_MIN_WAVE`);
   the reasons are in the report, section 3;
2. each night's median over the common window 11900-12450 Å (inside both
   J and J2) is compared with the era median of those medians; with at
   least 3 nights, a night more than 3 MAD away is excluded whole (D22);
3. per 1 Å pixel: the median of the remaining curves (`thru_median`), their
   median absolute deviation (`thru_mad`) and the count (`n_std`);
4. the `meta` lists the standards used and excluded and the distinct
   reduction provenance of the rows.

An era's curve covers only what its standards measured. At run time
{meth}`keck_etcs.instruments.base.Instrument.throughput_for_window`
completes a band window from the nearest era that measured the rest,
scaled by the median ratio of the two curves over 11900-12450 Å, with a
warning in the output (2025-04.. over J: 12462-13457 Å from 2017-2025
× 1.024). Beyond every era the edge value is held, also with a warning.

### 1.5 The other calibration inputs

| Input | File | Built by | Source |
|---|---|---|---|
| Sky background $B(\lambda; X, \mathrm{PWV})$ and transmission $T_{\rm atm}(\lambda; X, \mathrm{PWV})$ | `keck_etcs/data/sky/gemini_mk_sky_grid.fits` (HDUs `WAVE`, `SKYBG`, `TRANS`, `GRID`; 0.05 nm steps, 12 airmass × PWV rows) | `scripts/mosfire/build_gemini_sky_grid.py` | Gemini Observatory Maunakea IR sky and ATRAN models, as redistributed in Keck XTcalc; flux-conserving rebin |
| Filter curves $F(\lambda)$ | `keck_etcs/data/mosfire/filters/mosfire_<band>.ecsv` with `half_power_A` and `ab_minus_vega` in `meta` | `scripts/mosfire/` | Keck MOSFIRE filters page; (m_AB − m_Vega) is the synthetic AB magnitude of Vega through $F$ |
| Detector: read noise versus reads, gain, dark, linearity, minimum integration | `keck_etcs/data/mosfire/detector.ecsv` | `scripts/mosfire/build_detector_table.py` | Keck MOSFIRE detector page (D12); CDS 21 e⁻ confirmed at 21.4 e⁻ on our lamp-off flats |
| LSF rule | `LSF_SLOPE`, `LSF_FLOOR_PIX`, `LSF_FORM` in `instruments/mosfire.py`; measured rows in `keck_etcs/data/mosfire/lsf_measurements.ecsv` | calibration monitor (OH-line widths at 12500 Å, {mod}`keck_etcs.calib.monitor`) | 1" slit 3.56-3.61 pix on 4 nights, 0.7" slit 2.63 pix (D25) |
| Instrument constants | `instruments/mosfire.py` | | area and plate scale from PypeIt; band footprint from the 2022-04-09 `WaveCalib` |

Two PypeIt detector values were checked along the way. PypeIt's
`keck_mosfire` dark current (28.8 e⁻/pix/hr = 0.008 e⁻/s/pix) agrees with
Keck's page and is what the ETC uses. PypeIt's read noise was a single
5.8 e⁻ (MCDS-16) for every frame; the fix that takes it from
`SAMPMODE`/`NUMREADS` is on PypeIt's `etc-fixes` branch
(`nautilus/patches/pypeit_mosfire_ronoise.patch`, `CHANGES.md`).

## 2. The ETC chain: `compute`

{func}`keck_etcs.etc.compute` takes a dict that validates against
`keck_etcs/schema/etc_input.json` and returns every field of
`etc_output.json`. It imports only numpy, scipy, astropy, jsonschema and
pyyaml; the test suite and the documentation build prove that PypeIt is
not needed. The steps below follow the order of the code; the function
named in each heading is where the equation lives. "Design 5.3.x" refers
to the design document.

### 2.1 Pixel grid and LSF (design 5.3.6, D25)

The band window is the filter's half-power band intersected with the
detector footprint of the long slit (N2;
{meth}`keck_etcs.instruments.base.Instrument.band_window`). The pixel
centres are `wave_A` = $\lambda_{\rm lo} + k\,\Delta\lambda$
({func}`keck_etcs.core.lsf.pixel_grid`). The line-spread function is a
Gaussian whose FWHM in pixels is the measured value for that slit width when
`lsf_measurements.ecsv` has one, else the quadrature rule

$$
\mathrm{FWHM}_{\rm pix} = \sqrt{ (w / 0.292)^2 + 1.08^2 }, \qquad
\mathrm{FWHM}_{\rm lsf} = \mathrm{FWHM}_{\rm pix}\,\Delta\lambda, \qquad
R(\lambda) = \lambda / \mathrm{FWHM}_{\rm lsf}, \qquad
n_{\rm spec} = \mathrm{FWHM}_{\rm pix}
$$

({func}`keck_etcs.core.lsf.fwhm_pix`,
{meth}`keck_etcs.instruments.base.Instrument.lsf_fwhm_pix`). $n_{\rm spec}$
is the number of pixels per resolution element used for `snr_resel`.

### 2.2 Source spectrum and normalisation (design 5.3.1, 5.3.2)

The continuum shape is $F_\lambda \propto \lambda^{-2}$ (`flat_fnu`),
$\lambda^{-(\alpha+2)}$ (`power_law`, $f_\nu \propto \nu^\alpha$) or the
user's spectrum ({func}`keck_etcs.core.source.shape_flambda`). It is scaled
so that its synthetic AB magnitude through the band's filter equals
`source.mag`:

$$
m_{\rm AB} = -2.5\log_{10} \frac{\int f_\nu F\, d\nu}{\int F\, d\nu} - 48.6
= -2.5\log_{10} \frac{\int F_\lambda F\, d\lambda}{\int F\, (c/\lambda^2)\, d\lambda} - 48.6
$$

({func}`keck_etcs.core.source.mean_fnu`,
{func}`keck_etcs.core.source.normalize_to_mag`; `compute` evaluates the
integrals on the filter's own grid). A Vega magnitude is first converted
with $m_{\rm AB} = m_{\rm Vega} + (m_{\rm AB} - m_{\rm Vega})_{\rm band}$,
the offset being stored with the filter ({func}`keck_etcs.core.source.to_ab`).
An emission line is a Gaussian of integrated flux `flux_cgs` and intrinsic
FWHM $\lambda\,v_{\rm FWHM}/c$, binned flux-conservingly onto the fine grid
({func}`keck_etcs.core.source.gaussian_line_binned`), plus a flat-$f_\nu$
continuum at `continuum_mag` if given. For an extended source `source.mag`
is a surface brightness per arcsec² and the disk's flux is
$F_\lambda\,\pi D^2/4$ with $D$ = `size_arcsec`.

The photon rate above the atmosphere is

$$
N_0(\lambda) = \frac{F_\lambda(\lambda)\, A\, \lambda}{h c} \quad [\mathrm{photons/s/\mathring{A}}]
$$

({func}`keck_etcs.core.source.photon_rate`).

### 2.3 Atmosphere (design 5.3.3, N4)

$T_{\rm atm}(\lambda; X, \mathrm{PWV})$ is interpolated from the Gemini grid
bilinearly, linear in $X$ and linear in $\ln \mathrm{PWV}$
({func}`keck_etcs.core.atmosphere.interp_grid`,
{func}`keck_etcs.core.atmosphere.transmission`). A requested airmass or PWV
outside the grid is clipped to its edge and a warning is appended to the
output; nothing is raised.

### 2.4 System throughput (design 5.3.4)

$$
T_{\rm sys}(\lambda) = T_{\rm era}(\lambda)\; F(\lambda)\; s_{\rm thr}
$$

with $T_{\rm era}$ the era's filter-free curve of section 1.4 (completed
over the window as described there), $F$ the band's filter and
$s_{\rm thr}$ = `throughput.scale`. The era is chosen from
`throughput.date` ({meth}`keck_etcs.instruments.base.Instrument.era_for_date`;
the latest era without a date; a date in an instrument gap takes the era
before it, with a warning).

### 2.5 Convolution and sampling (design 5.3.6)

Everything is computed on the sky grid's uniform 0.5 Å fine grid, extended
10 LSF FWHM beyond the window, and then convolved with the Gaussian LSF and
sampled at the pixel centres ({func}`keck_etcs.core.lsf.convolve_to_pixels`,
{func}`keck_etcs.core.lsf.gaussian_convolve`; the kernel extends to
5 σ and the edges are renormalised by the convolved unit spectrum). The
**product** $N_0 T_{\rm atm} T_{\rm sys}$ is convolved, not each factor,
so an emission line sitting on a telluric feature is attenuated by the
unsmoothed transmission at its wavelength; for a smooth continuum the two
orders agree. The reported `throughput`, `atm_transmission` and
`filter_transmission` arrays are the separately convolved factors, for
display.

### 2.6 Sky (design 5.3.8, D14, N6)

The Gemini background $B(\lambda; X, \mathrm{PWV})$ is in
photons/s/arcsec²/nm/m² *as seen from the ground*, so $T_{\rm atm}$ is never
applied to it (N6). Scaled by `sky_scale` and interpolated like
$T_{\rm atm}$ ({func}`keck_etcs.core.sky.sky_background`), the rate per
spatial pixel in the slit and per spectral pixel is

$$
b(\lambda) = s_{\rm sky}\,\frac{B(\lambda)}{10}\; A_{\rm m^2}\; T_{\rm sys}(\lambda)\; w\; p\; \Delta\lambda
\quad [\mathrm{e^-/s\ per\ (spatial\ pix,\ spectral\ pix)}]
$$

({func}`keck_etcs.core.sky.sky_rate_per_pixel`; the /10 converts per nm to
per Å). $B\,T_{\rm sys}$ is convolved with the LSF before sampling, which is
what spreads each OH line over $\mathrm{FWHM}_{\rm pix}$ pixels. In the
aperture of $n_{\rm spat}$ spatial pixels and per frame,
$B_{\rm ap} = b\, n_{\rm spat}\, t$ ({func}`keck_etcs.core.sky.sky_in_aperture`).

### 2.7 Slit loss and extraction aperture (design 5.3.5, D16, D26)

The point-spread function is a circular Moffat of index $\beta = 3.5$ and
FWHM $s$:

$$
I(r) = \frac{\beta - 1}{\pi \alpha^2}\left[1 + \left(\frac{r}{\alpha}\right)^2\right]^{-\beta},
\qquad
\alpha = \frac{s}{2\sqrt{2^{1/\beta} - 1}},
$$

normalised to 1 over the plane. With $x$ across the slit and $y$ along it,

$$
f_{\rm slit}(w) = \int_{-w/2}^{w/2}\! dx \int_{-\infty}^{\infty}\! dy\, I = I_z\!\left(\tfrac12, \beta - 1\right),
\quad z = \frac{(w/2)^2}{(w/2)^2 + \alpha^2},
\qquad
f_{\rm slit,ap}(w, L) = \int_{-w/2}^{w/2}\! dx \int_{-L/2}^{L/2}\! dy\, I .
$$

$f_{\rm slit}$ is closed form, a regularised incomplete beta function
({func}`keck_etcs.core.slitloss.slit_fraction`). $f_{\rm slit,ap}$ is
integrated exactly in $y$ for each $x$ (again an incomplete beta function)
and by composite Simpson on a 0.01" grid in $x$
({func}`keck_etcs.core.slitloss.slit_aperture_fraction`); results are cached
by (FWHM, $w$, $L$). The output reports `slit_fraction` = $f_{\rm slit}$ and
`aperture_fraction` = $f_{\rm slit,ap} / f_{\rm slit}$. The aperture length
is $L$ = `aperture.length_fwhm` × $s$ (default 1.5, D16; the J0841
validation puts the best value at 2.2 with a 1 percent plateau from 1.5 to
2.4) or `aperture.length_arcsec`, and $n_{\rm spat} = \lceil L / p \rceil$.
The peak-pixel fraction $f_{\rm peak} = f_{\rm slit,ap}(w, p)$ is kept for
saturation. An extended source is a uniform disk of diameter $D$ convolved
with the Moffat: the mean over the disk of the point-source fraction for a
PSF centred at each point ({func}`keck_etcs.core.slitloss.extended_fraction`).
With `seeing_wave_um` set, the FWHM scales as $\lambda^{-0.2}$ from that
wavelength ({func}`keck_etcs.core.slitloss.seeing_at`) and the fractions
are interpolated between 7 nodes across the band.

### 2.8 Detector terms (design 5.3.9, D12, D13)

Read noise per pixel per frame comes from the Keck table by linear
interpolation in $\log_2 N_{\rm reads}$ ({func}`keck_etcs.core.detector.read_noise`;
CDS is $N = 1$, MCDS-$N$ uses $N$, {func}`keck_etcs.core.detector.effective_reads`).
Dark current $D$ = 0.008 e⁻/s/pix. In the aperture and per frame the dark
charge is $n_{\rm spat} D t$ and the read variance $n_{\rm spat}\,\mathrm{RN}^2$.

### 2.9 Signal, noise and S/N (design 5.3.7, 5.3.10, D15)

Per spectral pixel and per frame, in electrons summed over the aperture,

$$
S(\lambda) = N_0\, T_{\rm atm}\, T_{\rm sys}\; f_{\rm slit,ap}\; \Delta\lambda\; t
$$

({func}`keck_etcs.core.snr.signal_per_pixel`; in `compute` the convolved
product of section 2.5 stands for $N_0 T_{\rm atm} T_{\rm sys}$), and

$$
\mathrm{var}_1 = S + k\left(B_{\rm ap} + n_{\rm spat} D t + n_{\rm spat}\mathrm{RN}^2\right),
\qquad k = \begin{cases} 1 & \texttt{nod = stare} \\ 2 & \texttt{nod = ABBA} \end{cases}
$$

({func}`keck_etcs.core.snr.frame_variance`, {func}`keck_etcs.core.snr.nod_factor`):
in ABBA each frame is differenced against an equal-time sky frame, which
doubles the background, dark and read variance (D15). Over $N_f$ frames,

$$
\mathrm{SNR}_{\rm pix}(\lambda) = \frac{N_f S}{\sqrt{N_f\,\mathrm{var}_1}} = \sqrt{N_f}\,\frac{S}{\sqrt{\mathrm{var}_1}},
\qquad
\mathrm{SNR}_{\rm resel} = \mathrm{SNR}_{\rm pix}\sqrt{n_{\rm spec}}
$$

({func}`keck_etcs.core.snr.snr_pixel`, {func}`keck_etcs.core.snr.snr_resel`).
The summary values are the medians over the window. In line mode the
observed FWHM is $\sqrt{\mathrm{FWHM}_{\rm line}^2 + \mathrm{FWHM}_{\rm lsf}^2}$
({func}`keck_etcs.core.lsf.observed_line_fwhm`) and `snr_line` is
$\sum S_{\rm tot} / \sqrt{\sum \mathrm{var}_{\rm tot}}$ over the pixels
within ± FWHM$_{\rm obs}$/2 of the centre, a window that holds
$\mathrm{erf}(\sqrt{\ln 2})$ = 0.761 of a Gaussian line's flux
({func}`keck_etcs.core.snr.line_window`, {func}`keck_etcs.core.snr.line_snr`).

### 2.10 Exposure-time mode (N7)

With rates $s = S/t$, $\beta = B_{\rm ap}/t$, $d = n_{\rm spat} D$ and
$r_2 = n_{\rm spat}\mathrm{RN}^2$, requiring $\mathrm{SNR}_{\rm pix} = \rho$
after $N_f$ frames gives a quadratic in $t$,

$$
N_f s^2 t^2 - \rho^2 (s + k\beta + k d)\, t - k \rho^2 r_2 = 0,
\qquad
t = \frac{\rho^2 (s + k\beta + k d) + \sqrt{\rho^4 (s + k\beta + k d)^2 + 4 N_f s^2 k \rho^2 r_2}}{2 N_f s^2}
$$

({func}`keck_etcs.core.snr.solve_exptime`). For `snr_reference = pixel` or
`resel` the target is the band **median** S/N, so
{func}`keck_etcs.core.snr.solve_exptime_median` brackets the per-frame time
from the smallest per-pixel solution upward and finds the root of
median(SNR$_{\rm pix}(t)$) − ρ with Brent's method (the median rises
monotonically with $t$); for `resel`, ρ is first divided by
$\sqrt{n_{\rm spec}}$. For `line` the quadratic is solved on the sums over
the line window. The solved time is then run through the forward model, so
the output is self-consistent; warnings flag a time below the minimum
integration (1.455 s) or above 3600 s, or a target that cannot be reached.

### 2.11 Saturation (design 5.3.11)

Per frame, the brightest pixel is

$$
\mathrm{peak}_{e}(\lambda) = N_0 T_{\rm atm} T_{\rm sys}\, f_{\rm peak}\, \Delta\lambda\, t + b(\lambda)\, t + D\, t,
$$

maximised over $\lambda$, sky lines included, and converted to ADU with the
gain 2.15 e⁻/ADU; the flag is `ok`, `nonlinear_1pct`, `nonlinear_5pct` or
`saturated` at 26000, 37000 and 43000 ADU
({func}`keck_etcs.core.snr.saturation_peak`,
{func}`keck_etcs.core.detector.linearity_flag`). Persistence is not
modelled; a fixed warning is added whenever the flag is not `ok`.

### 2.12 Provenance in every output

`meta` carries `keck_etcs_version`, the `calib_version` and
`pypeit_version` recorded in the throughput file's `meta` and in
`keck_etcs/data/index.yaml`, the `era` used, and the fully defaulted
`inputs`. `warnings` lists every clip, completion, interim rule and
ignored field, in order, without duplicates. A front end should display
them.

## 3. Checks that tie the two chains together

- **Regression fixtures** (`keck_etcs/tests/data/reference_*.json`,
  `scripts/regen_regression_fixtures.py`): `compute` on the three example
  inputs must reproduce the frozen outputs to 1e-6; any change in the
  physics or the data is a deliberate regeneration with a note in
  `CHANGES.md`.
- **Validation** (`scripts/mosfire/validate_j0841.py`, design 6.1): the
  ETC against PypeIt's measured S/N on J0841+3814 (2022-04-09), 0.982 over
  the band and 0.990 between OH lines for the release `mosfire-J-2026.10`.
- **XTcalc** (`scripts/mosfire/compare_xtcalc.py`,
  [XTcalc bug](../XTcalc_bug.md)): the 2012-2016 era curve times the J
  filter is within 3 percent of Keck's 2012 curve after the 75 against
  72.37 m² aperture is accounted for.
- **Release checks** (`scripts/mosfire/verify_release.py`,
  `scripts/check_docs.py`): one calibration version everywhere, images and
  PypeIt pins consistent, README examples run as written.

The [tests and continuous integration](testing.md) page says which of these
run automatically.
