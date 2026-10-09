# keck_etcs: API note for WMKO

*For WMKO staff hosting a web front end. keck_etcs 0.2.5, calibration
`mosfire-J-2026.10`, 2026-10-09. The schemas
`keck_etcs/schema/etc_input.json` and `etc_output.json` are the contract. This
page summarises them; `scripts/check_docs.py` checks that it lists every
field.*

**Call.** `keck_etcs.etc.compute(inputs: dict) -> dict`. Both dicts are plain
JSON. The CLI `keck_etc INPUT.json [-o OUT.json] [--summary]` wraps the call.

**Footprint.** `keck_etcs.core` and `keck_etcs.etc` need only numpy, scipy,
astropy, jsonschema and pyyaml (`pip install keck_etcs`). They need no
PypeIt, no Nautilus and no S3 access, and they make no network call.

Every calibration product ships inside the package, under
`keck_etcs/data/`, registered in `index.yaml`: throughput, filters, sky grid,
detector table and LSF. A call writes nothing, reads only the package data,
and never reads the calibration monitor (below). The S3 bucket
`s3://keck-etcs` is private working storage for the reductions, not a
dependency.

**Inputs.** Wavelengths are vacuum Angstroms. A missing field takes its
default. An unknown field, or a value outside its range, raises
`keck_etcs.etc.InputError`, naming every offending field (the CLI exits 2).

| Field | Type, range | Default | Unit, meaning |
|---|---|---|---|
| `instrument` | `keck_mosfire` | `keck_mosfire` | PypeIt spectrograph name |
| `band` | `J`, `J2` | `J` | filter |
| `slit_width_arcsec` | 0.3-5.0 | 0.7 | arcsec, CSU long slit |
| `source.type` | `point`, `extended` | `point` | |
| `source.mag` | 5-30 | 20.0 | mag (total; per arcsec^2 if extended), in the band |
| `source.mag_system` | `AB`, `Vega` | `AB` | |
| `source.size_arcsec` | 0.2-20 | 1.0 | arcsec, top-hat diameter (extended only) |
| `spectrum.shape` | `flat_fnu`, `power_law`, `user`, `line` | `flat_fnu` | |
| `spectrum.alpha` | -5 to 5 | 0.0 | f_nu ~ nu^alpha |
| `spectrum.wave_A`, `spectrum.flux` | arrays, >= 2 | - | A; f_lambda in any units, normalised to `source.mag` (`user`) |
| `spectrum.line.wave_A` | > 0 | required | A, observed centre, inside the band |
| `spectrum.line.flux_cgs` | > 0 | required | erg/s/cm^2 (per arcsec^2 if extended) |
| `spectrum.line.fwhm_kms` | 10-5000 | 200 | km/s, intrinsic |
| `spectrum.line.continuum_mag` | 5-30 or null | null | mag, flat-f_nu continuum under the line |
| `seeing_fwhm_arcsec` | 0.3-3.0 | 0.7 | arcsec, at the band (or at `seeing_wave_um`) |
| `seeing_wave_um` | 0.4-2.5 or null | null | micron; FWHM ~ lambda^-0.2 from there |
| `exptime_s` | 1.455-3600 | 120 | s per frame |
| `n_frames` | 1-1000 | 4 | |
| `readout.mode` | `CDS`, `MCDS` | `MCDS` | UTR reserved |
| `readout.n_reads` | 1, 2, 4, ..., 128 | 16 | reads per group (CDS forces 1) |
| `nod` | `ABBA`, `stare` | `ABBA` | ABBA doubles the background variance |
| `airmass` | 1.0-2.5 | 1.2 | grid clipped to 1.0-2.0, with a warning |
| `pwv_mm` | 0.5-10 | 1.6 | mm; grid clipped to 1.0-5.0, with a warning |
| `sky_scale` | 0.3-3.0 | 1.0 | multiplies the Gemini sky emission |
| `aperture.length_fwhm` | 0.5-5 | 1.5 | extraction length / seeing FWHM |
| `aperture.length_arcsec` | > 0 or null | null | arcsec; overrides `length_fwhm` |
| `throughput.date` | `YYYY-MM-DD` or null | null | selects the instrument era; null = latest |
| `throughput.scale` | 0.1-2 | 1.0 | free factor on the throughput |
| `target_snr` | > 0 or null | null | if set, `exptime_s` is solved at fixed `n_frames` |
| `snr_reference` | `pixel`, `resel`, `line` | `pixel` | the S/N that `target_snr` refers to |

**Outputs.** Arrays are per spectral pixel on `wave_A` (the band's
half-power window on the detector). Electrons are per spectral pixel, in the
extraction aperture, summed over all frames, unless the name says
`per_frame`.

| Field | Unit, meaning |
|---|---|
| `meta.keck_etcs_version`, `meta.calib_version`, `meta.pypeit_version` | code version; calibration tag (`mosfire-J-YYYY.MM`); PypeIt that built the throughput |
| `meta.era`, `meta.inputs` | era of the throughput used; the inputs with defaults filled |
| `wave_A` | A (vacuum) |
| `dispersion_A_per_pix`, `lsf_fwhm_A`, `n_spec_per_resel` | A/pix; A; LSF FWHM in pixels |
| `resolving_power` | lambda / `lsf_fwhm_A` |
| `slit_fraction`, `aperture_fraction` | Moffat flux through the slit; fraction of that within the aperture |
| `n_spatial_pix`, `fwhm_arcsec_band` | pixels along the slit; arcsec, seeing at the band |
| `throughput`, `atm_transmission`, `filter_transmission` | system (incl. filter and `throughput.scale`); atmosphere; filter |
| `signal_e`, `sky_e`, `dark_e`, `read_noise_e`, `noise_e` | electrons (read noise: rms) |
| `snr_pixel`, `snr_resel` | S/N per pixel; per resolution element |
| `summary.snr_pixel_median`, `summary.snr_resel_median` | band medians |
| `summary.snr_line`, `summary.line_window_A` | line mode: S/N within +- FWHM/2; window in A (else null) |
| `summary.exptime_s`, `summary.n_frames`, `summary.total_time_s` | s per frame (solved if `target_snr`); frames; s |
| `saturation.peak_e_per_frame`, `saturation.peak_adu_per_frame`, `saturation.wave_A` | brightest pixel per frame in e- and ADU (gain 2.15) and its wavelength in A |
| `saturation.flag` | `ok`, `nonlinear_1pct` (26k ADU), `nonlinear_5pct` (37k), `saturated` (43k) |
| `warnings` | list of strings |

**Errors and warnings.** Only schema violations raise. Physics outside a
model's range is clipped and reported in `warnings`, never raised:

- airmass or PWV outside the sky grid;
- a slit width without a measured LSF (the D25 rule is used);
- throughput spliced from another era, or held at its edge;
- an unreachable `target_snr`, or a solved time below 1.455 s or above 3600 s;
- a line outside the band, or a user spectrum that does not cover the band;
- persistence above the 1 percent linearity limit;
- inputs ignored for the chosen mode.

The front end should show `warnings` to the user.

**Versions.** Code is semantic (`keck_etcs.__version__`). Calibration releases
are date tags, `mosfire-J-YYYY.MM`, in `index.yaml` and each file's metadata.
Every output echoes both versions and `pypeit_version`. `CHANGES.md` has one
section per calibration release, giving:

- the standards added and excluded;
- the era medians before and after;
- detector-table changes;
- the reduction images (tag, digest) and PypeIt pins behind it.

A calibration release is one commit touching only `keck_etcs/data/` and
`CHANGES.md`. Regression fixtures change only with a `CHANGES.md` line.

**Calibration refresh cycle.** New KOA standards are reduced on Nautilus
(`nautilus/README.md`), then harvested and merged into `standards.ecsv`.
Each era curve is the pixel-wise median of its standards, with 3-MAD
exclusion of whole nights. Then `index.yaml` is bumped to the new tag and
`CHANGES.md` written. WMKO picks up a release by upgrading the package; no
data download is involved. A release is cut when an era gains standards.

**Calibration monitor.** The file
`keck_etcs/data/mosfire/monitor/calib_monitor.ecsv` holds one row per
(night, frame or calibration group, metric, wavelength or line).

- **Columns:** `night`, `mjd`, `instrument`, `metric`, `source`, `frame`,
  `target`, `decker`, `slit_width`, `filter`, `wave_A`, `line_id`, `value`,
  `unit`, `err`, `n`, `airmass`, `pwv_fit`, `cards`, `flag`, plus
  provenance (`image`, `image_digest`, `pypeit_git_sha`,
  `keck_etcs_git_sha`, `job_name`, `s3_prefix`, `keck_etcs_version`).
- **Metrics:**
  - spatial FWHM (`fwhm_scalar_*`, `fwhmfit_pix`, `slitloss_gt1pct`);
  - dome-flat rate (`flat_rate`, `flat_rate_per_arcsec`);
  - OH line widths (`line_fwhm_*`, `line_R`, `line_fwhm_slope`);
  - OH fluxes (`line_flux*`).
- **Trend flags:** `trend_3mad` marks a night beyond 3 MAD of its era.

The monitor is an engineering record for trends: `compute()` never reads
it. A new instrument (LRIS next) adds a `MONITOR` config in its
`keck_etcs/instruments/<inst>.py`, registered in
`keck_etcs/calib/monitor_configs.py`. The config gives the FWHM and flat
nodes, `flat_kind` (`dome` or `internal`), the lamp cards and the line
lists. The rows and the table format stay the same.
