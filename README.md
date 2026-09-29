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

## Layout

- `keck_etcs/` — the Python package (`tests/` beneath it)
- `claude_prompts/` — task prompts and a dated log of the work
- `CLAUDE.md` — conventions for working in this repository

## Authors

- J. Xavier Prochaska
- Claude
