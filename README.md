# keck-etcs

[![Documentation](https://readthedocs.org/projects/keck-etcs/badge/?version=keck-mosfire)](https://keck-etcs.readthedocs.io/en/keck-mosfire/)

Exposure time calculators (ETCs) for the Keck spectrographs, grounded in
real, reduced data rather than design numbers. Throughputs come from
standard stars reduced with [PypeIt](https://github.com/pypeit/PypeIt), the
NIR sky from the Gemini Maunakea models, and the detector terms from Keck's
measured values. The ETCs can be refreshed as new data come in.

The first instrument is **Keck/MOSFIRE, J and J2 long-slit spectroscopy**.
The current code is `keck_etcs` 0.2.5, with calibration `mosfire-J-2026.10`.
The documentation, with an in-browser calculator, is at
<https://keck-etcs.readthedocs.io/en/keck-mosfire/> (the `latest` version follows `main`
once `keck-mosfire` is merged). The results are in
`reports/Keck_MOSFIRE_report_20261009.md`, the design in
`docs/keck_mosfire_design.md`, the interface for WMKO in
`docs/wmko_api_note.md`, and the release history in `CHANGES.md`.

## Installation

```
conda activate pypeit14      # pypeit14b on the Linux workstation
pip install -e .             # the ETC: numpy, scipy, astropy, jsonschema, pyyaml
pip install -e .[calib,test] # plus the calibration pipeline (PypeIt, matplotlib, boto3) and pytest
```

The ETC itself (`keck_etcs.core`, `keck_etcs.etc`) does not need PypeIt, S3
access or `KECK_ETCS_DATA`. Every calibration product it uses ships in the
package under `keck_etcs/data/`, registered in `keck_etcs/data/index.yaml`.
For the calibration pipeline, install PypeIt from the local checkout at the
pin in `nautilus/pypeit_pin.txt` (see `requirements.txt`).

## Usage

Python. Inputs and outputs are plain JSON dicts. Missing inputs take the
defaults of `keck_etcs/schema/etc_input.json`.

```python
from keck_etcs.etc import compute

out = compute({'band': 'J', 'slit_width_arcsec': 0.7,
               'source': {'type': 'point', 'mag': 20.0, 'mag_system': 'AB'},
               'seeing_fwhm_arcsec': 0.7, 'exptime_s': 120, 'n_frames': 4,
               'readout': {'mode': 'MCDS', 'n_reads': 16}, 'nod': 'ABBA'})
print(out['meta']['calib_version'], out['meta']['era'])       # mosfire-J-2026.10 2025-04..
print(round(out['summary']['snr_pixel_median'], 2))           # 4.47 (S/N per pixel, band median)
print(out['saturation']['flag'], out['warnings'][:1])

# Solve for the exposure time: S/N 5 per resolution element in 8 frames
t = compute({'band': 'J2', 'source': {'mag': 21.0}, 'n_frames': 8,
             'target_snr': 5, 'snr_reference': 'resel'})
print(round(t['summary']['exptime_s'], 1))                    # 237.1 (s per frame)
```

Command line. The input is a JSON file; `examples/` holds three of them.

```
keck_etc examples/J_point.json --summary          # short report
keck_etc examples/J_point.json -o out.json        # full output (etc_output.json)
python bin/keck_etc examples/J_point.json --summary   # from a checkout without installing
```

`--summary` prints:

```
keck_etcs 0.2.5 | keck_mosfire J | calib mosfire-J-2026.10 | era 2025-04..
window 11534.7-13522.1 A, 1539 pix at 1.2922 A/pix; LSF 2.63 pix (R 3687)
...
band-median S/N per pixel 4.473, per resolution element 7.253
```

`throughput.date` (`YYYY-MM-DD`) selects an instrument era (2012-04..2016-09,
2017-02..2025-02, 2025-04..). Without it, the latest era is used. Every
output carries `warnings`: clipped airmass or PWV, LSF from the interim rule,
throughput completed from another era, and so on. Show them to the user.

## Data root

Raw frames, PypeIt reductions and external inputs are kept outside the
repository, under `KECK_ETCS_DATA` (default
`~/Projects/PypeIt/keck-etcs-data`). Only the calibration pipeline and the
validation scripts read it; the ETC never does.

```
$KECK_ETCS_DATA/
  external/xtcalc/XTcalc_dir/                         # Keck XTcalc tarball, unpacked (Gemini sky grids)
  mosfire/<YYYYMMDD>/{raw,redux,sens,harvest}/        # per-night data
  mosfire/<YYYYMMDD>/run_manifest.json, run.log
```

The canonical store is the private Nautilus S3 bucket `s3://keck-etcs`
(override with `KECK_ETCS_BUCKET`). The per-night part of the data root is a
local *mirror* of the bucket with the same layout:
`$KECK_ETCS_DATA/mosfire/20220409/sens` is `s3://keck-etcs/mosfire/20220409/sens`.
`scripts/nautilus/s3_sync.py pull` fills it. `external/` is local only.
`keck_etcs.paths` (`data_root()`, `night_dir()`, `s3_prefix()`) resolves
both layouts from the same parts, so the two cannot drift. FITS, `.sav` and
`.tar` files are git-ignored except under `keck_etcs/data/` and
`keck_etcs/tests/data/`.

## Calibration monitor

`keck_etcs/data/mosfire/monitor/calib_monitor.ecsv` is a long table with
one row per (night, frame or calibration group, metric, wavelength or line).

- **Written by:** the in-pod harvest (`harvest/<night>_monitor.ecsv`).
- **Merged by:** `scripts/mosfire/harvest_sens.py --merge`.
- **Columns:** `night, mjd, instrument, metric, source, frame, target,
  decker, slit_width, filter, wave_A, line_id, value, unit, err, n,
  airmass, pwv_fit, cards, flag`, plus the reduction provenance (`image,
  image_digest, pypeit_git_sha, keck_etcs_git_sha, job_name, s3_prefix`)
  and `keck_etcs_version`.
- **Metrics:**
  - spatial FWHM of standards and science objects (`fwhm_scalar_pix`,
    `fwhm_scalar_arcsec`, `fwhmfit_pix`, `slitloss_gt1pct`);
  - the dome-flat rate at fixed wavelengths (`flat_rate`,
    `flat_rate_per_arcsec`);
  - OH line widths (`line_fwhm_pix`, `line_fwhm_A`, `line_R`,
    `line_fwhm_slope`);
  - OH line fluxes, the sky monitor (`line_flux`, `line_flux_window`,
    `line_flux_above`, `line_flux_sum`).
- **Trend flags:** at a release, `flag` gains `trend_3mad` for a night
  more than 3 MAD from its era median. These are flags, not gates.
- **Plots:** `scripts/mosfire/plot_monitor_trends.py`.

`compute()` never reads this table.

**Adding an instrument (LRIS next).** Write its `keck_etcs/instruments/<inst>.py`
with a `MONITOR` config and register it in
`keck_etcs/calib/monitor_configs.py`. The config gives:

- the FWHM nodes and the flat nodes;
- `flat_kind` (`dome` or `internal`);
- the lamp header cards to record;
- the line lists and the frozen monitor lines.

`keck_etcs.calib.monitor` and the table format are instrument-agnostic.

## Refreshing calibrations

1. **Reduce** new standard nights on Nautilus: KOA download, night Job,
   failure sweep, sync back, backup. The operator guide is
   `nautilus/README.md`.
2. **Harvest and merge.** Pull each night's `harvest/` and run
   `python scripts/mosfire/harvest_sens.py --merge <night>/harvest ...`. This
   updates `standards.ecsv`, the per-standard curves and
   `calib_monitor.ecsv`.
3. **Combine and check.** Set `CALIB_VERSION` in
   `scripts/mosfire/combine_throughput.py` to the new tag
   (`mosfire-J-YYYY.MM`), then run it. It rebuilds the era curves and bumps
   their `index.yaml` entries.
4. **Plot and verify:**
   - `scripts/mosfire/plot_throughput_trend.py`;
   - `scripts/mosfire/plot_monitor_trends.py` (sets the `trend_3mad`
     flags);
   - `scripts/mosfire/verify_release.py` (must print ALL CHECKS PASS);
   - `scripts/regen_regression_fixtures.py --regen --note "why"` when
     outputs change (the note goes into `CHANGES.md`).
5. **Write the `CHANGES.md` section:**
   - the standards added and excluded;
   - the era medians before and after;
   - the detector-table changes;
   - the image tags, digests and PypeIt pins of the reductions.
6. **Commit and freeze.** Commit `keck_etcs/data/` and `CHANGES.md` as one
   release commit, and tag it with the calibration version. Run
   `scripts/nautilus/backup_products.py --run --release <tag>` to freeze the
   inputs on the backup drive.
7. **Documentation.** The push triggers a Read the Docs build. Check that
   the banner of the published site shows the new code and calibration
   versions, and that the interactive calculator reports them
   (`scripts/etc_page_check.py --url <published etc.html>`).

## Layout

- `keck_etcs/`: the package.
  - `core/`: physics; no I/O.
  - `instruments/`: per-instrument config and data access.
  - `calib/`: harvest, combine, trend, monitor.
  - `etc.py`: `compute`.
  - `schema/`: the JSON schemas.
  - `data/`: shipped products.
  - `tests/`.
- `bin/keck_etc`: the CLI.
- `examples/`: input JSON files.
- `scripts/`: calibration, validation and KOA scripts (`mosfire/`, `koa/`,
  `nautilus/`).
- `nautilus/`: the container image, Job manifests and operator guide.
- `docs/`: the design, the implementation plan, the WMKO note, the XTcalc
  notes and the figures.
- `reports/`: the MOSFIRE report and its figures.
- `claude_prompts/`: task prompts and a dated log of the work.
- `CLAUDE.md`: conventions for working in this repository.

## Tests

```
pytest keck_etcs/tests                # unit, schema and regression tests
pytest -m slow --run-slow             # the J0841 validation only (needs KECK_ETCS_DATA)
```

## Authors

- J. Xavier Prochaska
- Claude
