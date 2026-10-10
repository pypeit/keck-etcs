# Citing and versions

**Two versions describe every number.** `keck_etcs` separates the code from
its calibration, and every output of {func}`keck_etcs.etc.compute` reports
both:

- `meta.keck_etcs_version`: the code, a semantic version (here
  `keck_etcs.__version__`);
- `meta.calib_version`: the calibration release, a date tag such as
  `mosfire-J-2026.10`. A release changes only the shipped data
  (`keck_etcs/data/`) and is described in the [release notes](changes.md):
  the standards used, the era medians, and the reduction images and PypeIt
  versions behind them;
- `meta.era`: the instrument era whose throughput was used (set by
  `throughput.date`);
- `meta.pypeit_version`: the PypeIt version that built the throughput.

The banner at the top of every page of this site shows the code and
calibration versions it was built from. The interactive calculator and the
[examples](examples.md) report the versions of the actual calculation.
When you quote an ETC prediction, quote these versions too; a later
calibration release can change it.

**Citing.** Until a DOI is minted, cite the software through the
`CITATION.cff` file of the [repository](https://github.com/pypeit/keck-etcs)
(GitHub's "Cite this repository" button), and give the versions above. The
reductions use [PypeIt](https://pypeit.readthedocs.io) (Prochaska et al. 2020,
JOSS 5, 2308).

**Official tool.** W. M. Keck Observatory will host the observatory's
official web front end. This site documents the library behind it, its
calibration and validation, and offers an in-browser calculator for
convenience.
