# Keck/MOSFIRE J-band ETC: first calibration release, library and site

This PR turns the empty repository into a working exposure time calculator
for Keck/MOSFIRE J and J2 long-slit spectroscopy, with its throughput
measured from standard stars that we reduced ourselves with PypeIt, and
with the infrastructure to keep it current. It is `keck_etcs` 0.2.5 and
the calibration release `mosfire-J-2026.10`.

## What is in it

**A throughput measurement from real data, not design numbers.**
20 standard-star nights from KOA (2014-2025, white dwarfs and A0V telluric
stars through slits of 3" or wider) were reduced with PypeIt in Kubernetes
pods on Nautilus and turned into per-night zero points and end-to-end
throughput curves (`keck_etcs/calib/harvest.py`). 14 nights enter the
release, combined per instrument era (`combine.py`): the filter-free
throughput over 11900-12450 A is 0.258, 0.257 and 0.270 in the eras
2012-04..2016-09, 2017-02..2025-02 and 2025-04.., with no measurable
decline within an era (-0.3 +/- 0.5 percent per year in 2017-2025). The
curves, the per-standard table, the Gemini sky and transmission grid, the
filter curves and the detector table ship in `keck_etcs/data/` with their
provenance in `index.yaml` (image digests, PypeIt commits).

**A pure-Python ETC with a JSON interface.** `keck_etcs.etc.compute(dict)
-> dict`, validated against `keck_etcs/schema/etc_input.json` and
`etc_output.json`, with a CLI (`bin/keck_etc`) and three example inputs.
It models the source (AB or Vega, continuum shapes, user spectra, emission
lines, point or extended), the Gemini sky and transmission interpolated in
airmass and PWV, Moffat slit loss with an explicit extraction aperture, a
Gaussian LSF fitted to OH lines, the Keck read-noise table versus number of
reads, stare and ABBA noise, the exposure-time inversion, and saturation
flags. The core (`keck_etcs/core/`) has no I/O and needs only numpy,
scipy, astropy, jsonschema and pyyaml; two tests prove `compute` never
imports PypeIt. This is the library WMKO's web front end will call
(`docs/wmko_api_note.md`).

**Validation.** On J0841+3814 (2022-04-09, 4 x 150 s ABBA) the ETC
reproduces PypeIt's measured S/N to 0.982 over the band and 0.990 between
OH lines (criteria 20 and 10 percent). The throughput agrees with Keck's
2012 XTcalc curve to 3 percent. The comparison with XTcalc also found an
indexing quirk in XTcalc's magnitude mode (`docs/XTcalc_bug.md`).

**A calibration monitor.** Every reduced night also yields spatial FWHM,
dome-flat rates, OH line widths and OH line fluxes
(`keck_etcs/calib/monitor.py`, `keck_etcs/data/mosfire/monitor/`), so
instrument changes can be seen between calibration releases.

**Reproducible reductions.** `nautilus/` holds the container image
(PypeIt pinned by commit, telluric grid baked in), the KOA download and
night Jobs, the failure sweep and the operator guide; `scripts/koa/` holds
the KOA census and download tools; `scripts/mosfire/` the reduction,
sensfunc, harvest, combine, trend, validation and release-check scripts.

**Documentation.** A Sphinx site (Read the Docs, `docs/`) with an
in-browser calculator running the same `compute` under Pyodide, executed
examples, the WMKO API note, the generated field reference, the design
document and implementation plan, the MOSFIRE report
(`reports/Keck_MOSFIRE_report_20261009.md`), and developer pages on how
the calculations are performed (equation by equation, with the PypeIt
code behind each step) and on tests and CI.

**Tests and CI.** 111 fast tests (physics, schemas, `compute`, regression
against frozen example outputs, the calibration modules) plus a slow
validation test against the in-pod products. `.github/workflows/ci.yml`
runs the suite without PypeIt on Python 3.11-3.14, with PypeIt at the
pinned commit, and builds the documentation with warnings as errors.

## Changes made to PypeIt along the way

- MOSFIRE read noise now follows `SAMPMODE`/`NUMREADS` (CDS 21 e-, measured
  21.4 e- on our lamp-off flats; PypeIt had 5.8 e- for every frame). On the
  `etc-fixes` branch, patch in `nautilus/patches/`.
- Reduction fixes for MOSFIRE long slits and `long2pos_specphot` masks, all
  pinned by commit in the image (`nautilus/pypeit_pin.txt`).

## Known systematics (report, section 5)

A J/J2 offset of about 5 percent; the tabulated J filter cut-on; the A0V
depression blueward of 11900 A; the sky continuum between OH lines at
1.14-1.34x the Gemini model on the one validation night. These are
recorded in `CHANGES.md` and the report and are the first items for the
next calibration release.

## How to try it

```
pip install -e .
python bin/keck_etc examples/J_point.json --summary
pytest keck_etcs/tests
```

Docs: https://keck-etcs.readthedocs.io/en/keck-mosfire/

🤖 Generated with [Claude Code](https://claude.com/claude-code)
