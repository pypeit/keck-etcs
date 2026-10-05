# Changes

Code versions follow `keck_etcs.__version__`; calibration releases are tagged
`mosfire-J-YYYY.MM` (design 5.5, D28). A calibration release is one commit
touching only `keck_etcs/data/` and this file, with a section listing the
standards added, the era medians before and after, any detector-table
change, and the image tags (with digests) of the Nautilus reductions that
fed it.

## Calibration releases

None yet. The ETC currently runs on the PROVISIONAL throughput
`provisional-xtcalc-2012` (XTcalc 2012, `keck_etcs/data/mosfire/throughput/
mosfire_thru_provisional-xtcalc-2012.ecsv`), which must be replaced by the
S10 per-era curves before any release.

## Regression fixtures

- 2026-10-04: regression fixtures regenerated (keck_etcs 0.1.6, throughput provisional-xtcalc-2012): first freeze (S9): examples J_point, J2_point, J_line against the provisional XTcalc throughput
