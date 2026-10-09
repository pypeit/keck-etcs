# Changes

Code versions follow `keck_etcs.__version__`; calibration releases are tagged
`mosfire-J-YYYY.MM` (design 5.5, D28). A calibration release is one commit
touching only `keck_etcs/data/` and this file, with a section listing the
standards added, the era medians before and after, any detector-table
change, and the image tags (with digests) of the Nautilus reductions that
fed it.

## Code (unreleased, after 0.2.5)

- **Packaging (S18):**
  - `install_requires` is now what `keck_etcs.core` and `keck_etcs.etc`
    import: numpy, scipy, astropy, jsonschema and pyyaml;
  - PypeIt, matplotlib, IPython and boto3 move to the `calib` extra, and
    pytest to `test`;
  - `package_data` now also ships the per-standard curves
    (`keck_etcs/data/mosfire/throughput/standards/`), so a wheel holds all
    40 files of `keck_etcs/data/`.
- **PypeIt (S17):** `KeckMOSFIRESpectrograph.get_detector_par` takes
  `ronoise` from `SAMPMODE`/`NUMREADS` (Keck table; CDS 21 e-, was 5.8 for
  every frame).
  - Committed on `etc-fixes` as `38bb1b747d55a5b9205cbeb62734b0e870223990`;
    the patch is `nautilus/patches/pypeit_mosfire_ronoise.patch`.
  - Not yet pinned. The next image (0.2.6) should pin it. No released
    product uses it.
  - A CDS lamp-off flat pair gives 21.4 e- (`measure_read_noise.py`).
- **Docs (S18):**
  - `README.md` usage;
  - `nautilus/README.md` as the operator guide;
  - `docs/wmko_api_note.md`;
  - the design document "as built" (v0.5);
  - `scripts/check_docs.py`, which checks that the docs agree.

## Calibration releases

### mosfire-J-2026.10 (2026-10-08, plan S16; first release)

**Era curves** (`keck_etcs/data/mosfire/throughput/mosfire_thru_<era>.ecsv`,
`scripts/mosfire/combine_throughput.py`; filter-free, pixel-wise median):

| Era | Standards used | Range [A] | Curve median 11900-12450 A | Before |
|---|---|---|---|---|
| 2012-04..2016-09 | 4 | 11633-13457 | 0.257 | none (used 2017-2025) |
| 2017-02..2025-02 | 9 | 11172-13457 | 0.255 | 0.273 (LDS749B only, S10) |
| 2025-04.. | 1 | 11171-12462 | 0.270 | none (used 2017-2025) |

- 2017-02..2025-02 at 11600 / 12000 / 12400 A: 0.186 / 0.244 / 0.273 before,
  0.185 / 0.251 / 0.264 now; it now also covers 12462-13457 A.
- The ETC (`compute`) completes an era's curve over the band window from
  the nearest era that measured the rest, scaled by the median ratio over
  11900-12450 A (`Instrument.throughput_for_window`; 2025-04.. over J:
  12462-13457 A from 2017-2025 x 1.024; 2012-2016 over J2: 11172-11633 A
  x 1.005).
- The default (latest) era is now 2025-04.., one standard.

**Standards added:** 15 nights over S15a-S15b (`standards.ecsv` now has 20
rows; 14 enter the era curves).

- 2012-04..2016-09: Feige110 2014-06-01, HD95126 2014-11-23, HD18571
  2015-09-04, HD54601 2015-10-22.
- 2017-02..2025-02: HD74721 2017-11-05 and 2017-11-06, HD65158 2020-11-26,
  HD21379 2021-09-30, HD210501 2021-10-27, Feige110 2024-07-21, GD153
  2024-12-29 (J) and 2024-12-30 (J2), with LDS749B 2022-04-09 (S10).
- 2025-04..: GD153 2025-07-23.
- **Excluded:**
  - by the 26k ADU nonlinearity flag (harvest): HD159008 2015-04-28,
    HD74721 2016-04-17, HD133772 2017-06-15, HD21379 2021-09-28;
  - by 3 MAD on 11900-12450 A (D22): 55 Dra 2014-10-05 (0.196, J = 6.2 in
    1.45 s frames) and GD153 2025-01-25 (0.285; the J2 nights sit about
    5 percent above J, below).

**Method changes** (S16; Q&A S16-1 to S16-3):

- J rows only where the J filter is >= 0.9 of its peak; A0V rows only
  redward of 11900 A (`combine.EDGE_TRIM_FRAC`, `A0V_MIN_WAVE`). Reasons:
  - the J curve of the same white dwarf falls below its J2 curve by
    10 percent at 11650 A (the tabulated J cut-on is too high);
  - every A0V curve is depressed blueward of about 11900 A.
- The 3-MAD exclusion compares nights over 11900-12450 A, inside both
  filters.
- **D25 LSF:** `FWHM = sqrt((w / 0.292)^2 + 1.08^2)` pix (was
  `max(w / 0.277, 2.2)`); +3.9 percent at 0.7", -0.6 percent at 1.0"
  (measured 1" widths still take precedence).
- **D14 `sky_scale`:** unchanged (1.0); OH lines over Gemini per night
  0.43-0.91 (median 0.82), continuum not monitored.

**Known systematics:**

- J/J2 offset of about 5 percent in 11900-12450 A (filter curves agree
  with the measured J2/J ratio to 3-9 percent).
- The J cut-on and A0V blue depression above.
- 55 Dra low but unflagged.
- `zp_1250` against airmass in J: 1.9 sigma (limit 2).
- 2012-2016 is +3.6 percent above XTcalc's 2012 curve (x 75 / 72.37 m^2;
  -10 to +15 percent in 250 A bins).

**Detector table:** unchanged.

**Validation against this release** (S18, 2026-10-09;
`scripts/mosfire/validate_j0841.py` on the unchanged 0.1.6 products):

- J0841+3814 2022-04-09, ETC/measured S/N: 0.982 over the band and 0.990
  between OH lines. Both pass (20 and 10 percent); they were 0.996 and 1.003
  with the S10 curve.
- XTcalc comparison (`compare_xtcalc.py`): ratios 0.895-1.013 (0.7") and
  1.078-1.291 (1.0"); they were 0.891-1.005 and 1.067-1.271.

**Reductions used** (image | digest | PypeIt pin):

- `keck-etcs:0.1.6` | sha256:0c5e88fd838e24f9e658be3a01ffee276d80546df772a9da19da9c0ce912a357 | 8017f47997d6417d797be6d0a0358d7acb8918b5
- `keck-etcs:0.2.2` | sha256:920bd25f80483fe1c47ae70605bbd299229e6ecb593ca29f31fe5ebdfd746138 | fb4790520e4ccd49d39d42ed8438a614f307030b
- `keck-etcs:0.2.3` | sha256:99cc0d6379326b165270eba073a8b12ac716d71965a406781fe8a9293da42adf | fb6fb62c46383b09c5c13f1edcad97d3367fa0cd
- `keck-etcs:0.2.4` | sha256:258e52f474676199e52a9a3969861445c542fcc6790940792e9de5ccac31d13b | fb6fb62c46383b09c5c13f1edcad97d3367fa0cd
- `keck-etcs:0.2.5` | sha256:69591fcbdb595ca0b24438f9b4cf803d0ad48dedbe36141a8d211e3b3a4daed4 | bc18a3ba46d1d331da0875424c63999e578a4937

All images are under `gitlab-registry.nrp-nautilus.io/profx/`. Checks:
`scripts/mosfire/verify_release.py` (ALL CHECKS PASS).

### mosfire-J-2026.10-dev (development products, not a release)

- 2026-10-05 (S10): first per-era throughput,
  `keck_etcs/data/mosfire/throughput/mosfire_thru_2017-2025.ecsv` (era
  2017-02..2025-02), from one standard: LDS749B on 2022-04-09 (J2, 5" slit,
  MF.20220409.55932+MF.20220409.56084), reduced in-pod with image
  `gitlab-registry.nrp-nautilus.io/profx/keck-etcs:0.1.6`
  (`sha256:0c5e88fd838e24f9e658be3a01ffee276d80546df772a9da19da9c0ce912a357`,
  keck-etcs `b2883b6`), PypeIt pin `8017f47997d6417d797be6d0a0358d7acb8918b5`.
  It covers 11172-12462 A (J2 half-power band); band median 0.227
  (filter-free). Eras 2012-04..2016-09 and 2025-04.. have no standards yet
  and use it with a warning. It replaces the provisional XTcalc 2012 curve
  (`provisional-xtcalc-2012`, part 3 S9), which is removed.

## Regression fixtures

- 2026-10-08: regression fixtures regenerated (keck_etcs 0.2.5, throughput mosfire-J-2026.10): S16 first calibration release mosfire-J-2026.10: era curves for 2012-04..2016-09, 2017-02..2025-02 and 2025-04.. from 14 standards (combine cuts S16-1(b): J rows T >= 0.9 peak, A0V rows >= 11900 A; 3-MAD on 11900-12450 A); the default (latest) era is now 2025-04.., completed over J from 2017-2025 (Instrument.throughput_for_window); D25 LSF quadrature refit sqrt((w/0.292)^2 + 1.08^2) pix (+3.9 percent at 0.7 arcsec)
- 2026-10-04: regression fixtures regenerated (keck_etcs 0.1.6, throughput mosfire-J-2026.10-dev): S10: throughput mosfire_thru_2017-2025.ecsv (mosfire-J-2026.10-dev) replaces provisional-xtcalc-2012; LDS749B 2022-04-09 row from image keck-etcs:0.1.6 (sha256:0c5e88fd...2a357), PypeIt pin 8017f47; era names now 2017-02..2025-02 style
- 2026-10-04: regression fixtures regenerated (keck_etcs 0.1.6, throughput provisional-xtcalc-2012): first freeze (S9): examples J_point, J2_point, J_line against the provisional XTcalc throughput
