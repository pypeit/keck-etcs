# Changes

Code versions follow `keck_etcs.__version__`; calibration releases are tagged
`mosfire-J-YYYY.MM` (design 5.5, D28). A calibration release is one commit
touching only `keck_etcs/data/` and this file, with a section listing the
standards added, the era medians before and after, any detector-table
change, and the image tags (with digests) of the Nautilus reductions that
fed it.

## Calibration releases

None yet (the first is S16, `mosfire-J-2026.10`).

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

- 2026-10-04: regression fixtures regenerated (keck_etcs 0.1.6, throughput mosfire-J-2026.10-dev): S10: throughput mosfire_thru_2017-2025.ecsv (mosfire-J-2026.10-dev) replaces provisional-xtcalc-2012; LDS749B 2022-04-09 row from image keck-etcs:0.1.6 (sha256:0c5e88fd...2a357), PypeIt pin 8017f47; era names now 2017-02..2025-02 style
- 2026-10-04: regression fixtures regenerated (keck_etcs 0.1.6, throughput provisional-xtcalc-2012): first freeze (S9): examples J_point, J2_point, J_line against the provisional XTcalc throughput
