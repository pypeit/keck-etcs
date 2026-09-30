# keck-etcs

Generate and then update exposure time calculators (ETCs) for the Keck
spectrographs.

Throughputs, sky, and detector properties are grounded in real, reduced data
(sensitivity functions and calibrations from
[PypeIt](https://github.com/pypeit/PypeIt)) rather than design numbers, so the
ETCs can be refreshed as new data come in.

## Installation

```
conda activate pypeit14
pip install -r requirements.txt
pip install -e .
```

## Data root

Raw frames, PypeIt reductions and external inputs are kept outside the
repository, under the directory named by the environment variable
`KECK_ETCS_DATA` (default `~/Projects/PypeIt/keck-etcs-data`):

```
$KECK_ETCS_DATA/
  external/xtcalc/XTcalc_dir/                   # Keck XTcalc tarball, unpacked (Gemini sky grids)
  mosfire/<YYYYMMDD>/{raw,redux,sens,harvest}/  # per-night data
```

The canonical store is the private Nautilus S3 bucket `s3://keck-etcs`
(override with `KECK_ETCS_BUCKET`). The per-night part of the data root is a
local *mirror* of that bucket with the same layout: `$KECK_ETCS_DATA/mosfire/20220409/sens`
corresponds to `s3://keck-etcs/mosfire/20220409/sens`. `external/` is local
only. `keck_etcs.paths` (`data_root()`, `night_dir()`, `s3_prefix()`)
resolves both, so the two layouts cannot drift. FITS, `.sav` and `.tar`
files are git-ignored except under `keck_etcs/data/` and
`keck_etcs/tests/data/`.

## Layout

- `keck_etcs/` — the Python package (`tests/` beneath it)
- `claude_prompts/` — task prompts and a dated log of the work
- `CLAUDE.md` — conventions for working in this repository

## Authors

- J. Xavier Prochaska
- Claude
