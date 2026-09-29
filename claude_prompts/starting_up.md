# Getting started

## Goals

This repository will generate, and then keep updated, exposure time calculators
(ETCs) for the Keck spectrographs (e.g. HIRES, ESI, DEIMOS, LRIS, MOSFIRE,
NIRES, NIRSPEC, KCWI).  The throughputs, sky, and detector properties should be
grounded in real, reduced data (PypeIt sensitivity functions and calibrations)
rather than stale design numbers, so the ETCs can be refreshed as new data come
in and shared with the community.

## Prompts

1. Read this file.  Execute the 1st task under "Claude/CLAUDE.md file"
2. Read this file.  Execute the 1st task under "Claude/Skills"
3. Read this file.  Execute the 1st task under "Claude/Settings"
4. Read this file.  Execute the 1st task under "Basic start up"
5. Read this file.  Execute the 1st task under "Context"

6. Read this file.  I have answered your Q&A; please read that and react accordingly.  Do not ask any more questions for now.  I am going to launch the effort in a different prompt doc. 

## Claude

### CLAUDE.md file

1. Examine all of the current files in the repository.  Then generate a basic
   CLAUDE.md file for this project.  Have it indicate:

    - I will perform git commands.  Read-only git (status, diff, log, show,
      branch) is fine; anything that changes repository state is mine to run.
    - If you do any calculation, generate it as a python script and write it to
      disk so that I can add it to the Repository.
    - If you need to run Python, use the "pypeit14" conda environment, invoked
      as `conda run -n pypeit14 python ...`.  Never the system Python.
    - The PypeIt source lives at `/Users/xavier/Projects/PypeIt/PypeIt` and the
      development suite at
      `/Users/xavier/Projects/PypeIt/PypeIt-development-suite`.  The Keck
      spectrograph definitions are in `pypeit/spectrographs/keck_*.py`, and
      sensitivity functions, extinction curves, and sky spectra are under
      `pypeit/data/` (`sensfuncs/`, `extinction/`, `sky_spec/`, `skisim/`).
      Consult these for instrument properties rather than guessing.
    - Read `claude_prompts/` before acting, and do only the numbered task you
      were pointed at.
    - Log your work in the Logs section of the relevant prompt doc.

### Skills

1. Copy over the skills/ files from the IOPtics repository
   (`/Users/xavier/Oceanography/python/IOPtics/.claude/skills`) into
   `.claude/skills/` here.  That is `critical-partner` and `grill-me`.

### Settings

1. Generate a `.claude/settings.json` for the project that allows you to run
   most bash commands and run Python (use the "pypeit14" conda environment).
   Start from `/Users/xavier/Projects/PypeIt/first-hires-exoplanet/.claude/settings.json`,
   which is already the IOPtics policy pruned and switched to `pypeit14`.
   Copy the policy, not any path-specific allow entries.  Keep the deny list,
   in particular `git push` / `git commit` / `git reset` / `git rebase`, so the
   permission system enforces the git rule above.

## Basic start up

1. Generate the basic files that one needs for a Python GitHub repository, e.g.
   a file for dependencies.  Examine the other Repositories in
   `Projects/PypeIt` (and `Oceanography/python` if useful) to see how I tend to
   organize things (`setup.py` + `requirements.txt` + `pytest.ini`, not
   `pyproject.toml`).  The package directory must be `keck_etcs` — the repo
   name has a hyphen, which is invalid in a module name.  Log your work in the
   Logs section.

## Context

1. Please explore and write a Report below.  Do no editing yet.  Cover:

    - What PypeIt already provides for each Keck spectrograph that an ETC
      needs: throughput / sensitivity functions (which instruments and
      gratings have them), detector properties (gain, read noise, dark
      current, plate scale, spectral dispersion), sky emission, and
      extinction at Maunakea.
    - Which instruments or modes have gaps, and where that information could
      come from instead (the Keck instrument pages, the existing Keck ETCs,
      KOA data we could reduce ourselves).
    - A proposed order for building the ETCs (which instrument first, and why),
      and a sketch of the common core an ETC for any of them would share.

### Report

*2026-09-29. Read-only survey of the local PypeIt checkout (2.0.2.dev1217) and
the development suite. Paths are relative to
`/Users/xavier/Projects/PypeIt/PypeIt/pypeit/` unless stated. Detector values
come from `get_detector_par(det)` with no header in `pypeit14`.*

**Bottom line.** PypeIt already provides most ETC ingredients: detector
parameters, dispersion templates, Maunakea optical extinction, the Keck
effective area, and code that converts a zeropoint to throughput. Three
ingredients are missing:
1. Measured throughput for anything other than DEIMOS.
2. A Maunakea sky *emission* spectrum.
3. Any slit-loss or resolution model.

There is no existing ETC code to build on.

#### What PypeIt provides, per instrument

The telescope values are shared by all instruments: `KeckTelescopePar`
(`telescopes.py:36`) gives a 10 m diameter, f/15, and
`eff_aperture = 72.3674` m².

In the table, gain is in e-/ADU, RN (read noise) in e-, dark current in
e-/pix/hr, and platescale in arcsec/pix, unbinned. Binning is read from the
`BINNING` header card. Dispersion is the median Å/pix of the `reid_arxiv`
templates, whose binning is not recorded (some look 2x-binned).

| Instrument | Detector params | Throughput (sensfunc) | Dispersion source | Dev-suite standards | Gaps |
|---|---|---|---|---|---|
| **DEIMOS** | 8 CCDs, 0.1185"/pix. Gain and RN per date and amp mode, from 62 WMKO logs in `data/spectrographs/keck_deimos/gain_ronoise/`. | **Yes**: 600ZD, 830G, 900ZD, 1200G, 1200B (`data/sensfuncs/`) | Templates (0.32–0.64 Å/pix), plus a grating optical model (`keck_deimos.py:1100-1197`) | 830G (G191B2B); 900ZD (Feige 110, `_sensfunc`/`_flux` tests); 600ZD (`_flux` test) | Slit loss; other gratings and tilts |
| **LRIS-B/R** (+ `_orig`, `_mark4`) | 2x2 amps, 0.135"/pix. LRIS-R gain and RN depend on date: pre-2020, 2020-06-30, post-2021 upgrade. | None | Templates for most gratings (e.g. R600 about 0.80 Å/pix) | Feige 34, Feige 110, GD71, G191B2B, HZ15, GD153 (mark4 R600/10000 has a `_sensfunc` test) | Throughput, including dichroics |
| **HIRES** (+ `_orig` before 2004-08) | 3-CCD mosaic, 0.135"/pix. Gain set by the `CCDGAIN` header (low 1.9–2.1, high 0.78–0.86). | None packaged. The dev suite has `sensfunc_archive/create_hires_sensfunc.py`, but its output is not in PypeIt. | `predict_ech_wave_soln()` (`core/wavecal/echelle.py:55`), orders 35–117 | Feige 110 (2 `_sensfunc` tests), BD+28d4211, G191-B2B, LDS749B, Feige 67. All RED cross-disperser. | Throughput and blaze; nothing for the BLUE cross-disperser |
| **ESI** | 0.1542"/pix, with per-order platescale 0.120–0.168. Gain 1.3, RN 2.5. | None | 10 orders, 3757–10925 Å | BD+28d4211, Feige 34, G191-B2B (tagged as *science*) | Throughput and blaze per order |
| **KCWI / KCRM** | Gain from the header, RN measured from overscan, so both need a header. Slice widths 1.358 / 0.679 / 0.339". KCRM dark current is None and its platescale is marked TODO. | None | BL, BM, BH2/3, RL, RM1/2, RH3 templates | GD50, Feige 110, G47-18, BD26d2606, Wolf 1346 (tagged as science) | Throughput, default gain and RN, KCRM platescale |
| **MOSFIRE** | 0.1798"/pix, gain 2.15. RN 5.8 is for 16-read mode only. Dark current 0.008 e-/s. Saturation is a 1e9 placeholder. | None | Y/J/H/K arc and OH templates | GD71 (Y, `_sensfunc` test), HIP 17971 (A0V; H, K), LDS749B (J2) | Throughput, RN as a function of read mode, saturation |
| **NIRES** | 0.15"/pix, gain 3.8, RN 5.0, dark 0.13 e-/s. Saturation 1e6 is marked "not sure". | None | 5 orders, 0.75–2.47 µm | GD153, HIP 116886 | Throughput |
| **NIRSPEC** (high / high_old / low) | high: 0.13"/pix, RN 11.6. low: 0.098"/pix. **high_old dark current is in e-/s, not e-/pix/hr** (a unit bug). | None | Echelle angle models for Y–L | **None** | Everything except the detector values |

#### Throughput

- **DEIMOS files.** Each file has WAVE, ZEROPOINT and THROUGHPUT extensions.
  ZEROPOINT is in AB mag, giving electrons/s/Å. THROUGHPUT is the end-to-end
  fraction (telescope + instrument + QE), peaking at 0.17 (1200B) to 0.29
  (830G). The headers have no airmass and no slit width.
- **DEIMOS provenance conflict.** The sensfunc README cites 2005/2010 frames,
  but the HISTORY cards for 1200G, 600ZD and 830G list 2023 frames.
- **Possible extinction in the zeropoint.** These were built with the `IR`
  algorithm, so the zeropoint may still include extinction at the standard's
  airmass. *Not verified.*
- **Reusable code** in `core/flux_calib.py`:
  - `zeropoint_to_throughput` (`:806`)
  - `Flam_to_Nlam` / `Nlam_to_Flam` (`:712`, `:740`)
  - `compute_zeropoint`
  - `get_sensfunc_factor` (`:197`, which handles exptime, airmass and
    extinction)
  - `SensFunc.compute_throughput` (`sensfunc.py:660`)

#### Sky

- **No Maunakea sky emission spectrum.** `sky_spec/paranal_sky.fits` covers
  0.3–1.0 µm, but it is Paranal and in "dimensionless" units. The LRIS
  `sky_spec` files are uncalibrated and meant for flexure only.
- **NIR ingredients:**
  - `skisim/rousselot2000.dat`: OH lines, 0.61–2.62 µm, relative intensities.
  - `skisim/mktrans_zm_{10,16,30,50}_10.dat`: Maunakea ATRAN *transmission*,
    0.9–5.6 µm, at 1.0 / 1.6 / 3.0 / 5.0 mm of water vapour. The water values
    are inferred from the Gemini file naming.
  - Helpers `oh_lines()` and `transparency()` in `wavemodel.py:156-233`.

#### Extinction

- `data/extinction/mkoextinct.dat` covers 0.3–1.2 µm (Buton+2013, SNfactory).
  PypeIt selects it automatically: `closest_extinction_file`,
  `core/atmextinction.py:70`.
- Beyond 1.2 µm PypeIt holds the edge value, so there is **no NIR continuum
  extinction**.

#### Where the gaps could be filled

- **Throughput.** Reduce the dev-suite standards listed in the table with
  `pypeit_sensfunc`, then add more standards from KOA (koa.ipac.caltech.edu).
  RAW_DATA is **not on this machine**: the dev suite's `RAW_DATA/` holds only
  `apf_levy`. The Keck instrument pages and the existing Keck ETCs can serve
  as cross-checks, not as the source.
- **Sky.** Optical: measure sky spectra from our own reduced science frames
  (PypeIt's sky model), flux them with the sensfunc, and average by moon phase.
  NIR: the Gemini Maunakea sky-background models (OH + thermal + continuum).
  These would pair with the ATRAN transmission files already in `skisim`.
- **Slit loss and resolution.** Compute these from a seeing profile and the
  slit width, with slit widths taken from the headers of the standard frames.

#### Proposed build order

1. **DEIMOS.** It is the only instrument with measured throughput already, in
   5 gratings. Building it tests the whole pipeline end to end, and the result
   can be validated against the existing Keck DEIMOS ETC. The first job is to
   settle the provenance and extinction questions above.
2. **LRIS.** It is heavily used, has many standards in the dev suite, and has
   a `_sensfunc` test to start from. It adds the dichroic.
3. **HIRES.** Two `_sensfunc` tests exist, and the echelle wavelength
   predictor already exists. It adds per-order blaze.
4. **MOSFIRE.** The first NIR instrument. It forces the NIR sky and thermal
   model.
5. **NIRES, ESI, KCWI/KCRM, NIRSPEC.** Ordered by how much is missing. NIRSPEC
   has no standards at all.

#### Common core

Every instrument would share the same `keck_etcs` structure:

- **`Instrument` config.** Built from the PypeIt `Spectrograph`: detector
  parameters, platescale, binning, and dispersion per mode.
- **`Throughput`.** Zeropoint(λ) → N_λ [e-/s/Å] for a source of given AB mag
  or f_λ, loaded from a PypeIt sensfunc file.
- **`Atmosphere`.** Extinction 10^(−0.4 k(λ) X), plus NIR transmission.
- **`Sky`.** Surface brightness(λ) per arcsec², multiplied by the slit width
  and the extraction aperture, and passed through the same zeropoint.
- **`SlitLoss`.** A seeing profile (Moffat or Gaussian) × slit width, plus
  the spatial extraction aperture.
- **`Noise` and S/N.** Per resolution element:
  S/N = S t / sqrt(S t + B t + n_pix (RN² + D t)).
  Inverted, the same formula gives the exposure time for a target S/N.
- **Validation tests.** Reproduce the measured S/N of reduced science frames
  from PypeIt `spec1d` outputs (`med_s2n`). Validating against real data,
  rather than against other ETCs, is what makes this repository distinct.

## Q&A

Questions that came up while running prompts #1–5. None of them blocked
prompts 1–4.

1. **Build order.** Should DEIMOS be first, as proposed in the Report? Or do
   you have a priority instrument (e.g. for an upcoming proposal or a
   community request)?
>A. Let's start with Keck/MOSFIRE (J-band) and Keck/LRIS with the 600 grism and 600/7500 grating
2. **DEIMOS sensfuncs.** Should we trust the archived files as they are, or
   regenerate them? The README (2005/2010) and the FITS HISTORY (2023)
   disagree on which frames were used. The `IR` algorithm may also leave
   extinction in the zeropoint. My recommendation is to regenerate at least one
   grating from a dev-suite standard and compare.
>A. We will start over
3. **Raw data.** The dev suite's `RAW_DATA/` holds only `apf_levy` on this
   machine. Should I get the Keck standards from the dev-suite data host, or
   from KOA? Either way it needs a download location with disk space.
>A. We are going to scour KOA for the raw data.  But all of that effort will be in a separate prompt doc
4. **Sky emission.** PypeIt has none for Maunakea. Are you OK with building
   the optical sky from our own reduced frames, and taking the NIR sky from
   the Gemini Maunakea models? Or do you have a preferred source?
>A. Yes, that is fine
5. **Deliverable form.** Should the result be a Python library, a CLI, a web
   page, or all three? "Shared with the community" suggests a web front end
   eventually, and that would shape the core API now.
>A. We will eventually provide a web based front-end for WMKO to host
6. **Validation standard.** Is matching the existing Keck ETCs a goal, or only
   a sanity check? The Report proposes validating against measured S/N from
   real reductions instead.
>A. It is only a sanity check
7. **PypeIt issues found in passing.** `keck_nirspec_high_old` has its dark
   current in e-/s rather than e-/pix/hr. The MOSFIRE and NIRES saturation
   values are placeholders. Should these be fixed in PypeIt proper, or worked
   around here?
>A. If they really are issues, we will fix them
8. **Housekeeping:**
   - I did not run `pip install -e .`. Please run it in `pypeit14`, or tell me
     to.
   - `.claude/settings.json` allows `python:*` (inherited from the template),
     which lets the system Python run despite the CLAUDE.md rule. Should I
     remove it?
   - Your other repos call this file `start_up.md`, not `starting_up.md`.
     Rename it?
>A. I have run the install.  The prompt doc is named ok.

## Logging

The "Logs" section will record Claude's work.  Please use the following format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

...

## Logs

### 2026-09-29 (Generated CLAUDE.md)

Examined every file in the repository. It is essentially empty: `README.md` (a
two-line title and tagline), `LICENSE` (BSD 3-Clause, "Copyright (c) 2026,
PypeIt"), the stock GitHub Python `.gitignore`, and this prompt doc. There is a
single commit, `bc20e1c "Initial commit"`, on branch `start-up`.

Created `CLAUDE.md` at the repo root with the same shape as
`first-hires-exoplanet/CLAUDE.md`, the closest PypeIt sibling:
- **Project:** the goal text from `## Goals`.
- **Workflow conventions:** git belongs to the user, and read-only git is
  permitted; calculations are written to disk as scripts; read
  `claude_prompts/` and do only the task pointed at; log dated entries here.
- **Environment:** `pypeit14`, invoked as `conda run -n pypeit14 python ...`.
- **Related repositories:** PypeIt (with the `keck_*.py` spectrographs and the
  `pypeit/data/` ETC ingredients) and the development suite.

What I learned:
- `pypeit14` is Python 3.14.6 and imports PypeIt 2.0.2.dev from the local
  checkout at `/Users/xavier/Projects/PypeIt/PypeIt` (an editable install). So
  PypeIt changes made there are visible here immediately.
- PypeIt defines 8 Keck spectrographs: deimos, esi, hires, kcwi, lris,
  mosfire, nires and nirspec.

No git commands were run other than read-only `git status` / `git ls-files`.

### 2026-09-29 (Copied skills from IOPtics)

Copied `critical-partner/` and `grill-me/` from
`/Users/xavier/Oceanography/python/IOPtics/.claude/skills` into
`.claude/skills/`. `.claude/` did not previously exist. Checked the copies
with `diff -r`: identical.

### 2026-09-29 (Generated .claude/settings.json)

Started from `first-hires-exoplanet/.claude/settings.json`. It is already the
IOPtics policy with the path-specific cruft removed and `ocean14` switched to
`pypeit14`, so there was nothing to prune. Changes:
- Fixed `$schema`: it pointed at the generic JSON-Schema meta-schema, not the
  Claude Code settings schema (`https://json.schemastore.org/claude-code-settings.json`).
- Added `pypeit_sensfunc` and `pypeit_flux_calib`. We will likely need to
  regenerate sensitivity functions from standards.
- Added WebFetch for `www2.keck.hawaii.edu` and `keckobservatory.org`, for the
  instrument pages and the existing Keck ETCs.

Kept the deny list intact (`sudo`, `rm -rf /`, `rm -rf ~`, `git push`,
`git commit`, `git reset`, `git rebase`), and `rm:*` stays in `ask`.

### 2026-09-29 (Basic Python repo files)

Modeled on `first-hires-exoplanet` (setup.py + requirements.txt + pytest.ini,
with tests beneath the package). Created:
- `setup.py`: name `keck_etcs`, BSD license, `python_requires>=3.11`,
  `find_packages()`, and `bin/` scripts picked up if that directory appears.
- `requirements.txt`: numpy, scipy, matplotlib, astropy, IPython, pytest and
  pypeit, with a note to install the local PypeIt checkout editable.
- `pytest.ini`: `testpaths = keck_etcs/tests`.
- `keck_etcs/__init__.py` (with `__version__`) and `keck_etcs/tests/__init__.py`.
- Rewrote `README.md` with a description, install steps, layout and authors.

Kept the existing `LICENSE` and `.gitignore` unchanged. Checked that
`import keck_etcs` works in `pypeit14`. `pytest` collects 0 tests (exit code
5), as expected for now. I did not run `pip install -e .`, because that is an
environment change for you to make.

### 2026-09-29 (Context survey: Report and Q&A)

Surveyed the local PypeIt checkout and the development suite, read-only, and
wrote the Report above. I then spot-checked the key claims myself: the file
listings of `sensfuncs/`, `sky_spec/` and `skisim/`, the provenance of
`mkoextinct.dat`, `zeropoint_to_throughput` at `flux_calib.py:806`, Keck's
`eff_aperture = 72.3674`, and the missing `RAW_DATA`. I did not check each
per-instrument detector value individually.

What I learned:
- **DEIMOS is the only Keck instrument with packaged throughput.** It is the
  natural first ETC.
- **PypeIt has no Maunakea sky emission spectrum**, and no NIR continuum
  extinction past 1.2 µm. These are the biggest gaps that are not specific to
  one instrument.
- **The dev suite's raw data is not on this machine**, so any sensfunc
  regeneration needs a download first.
- **Everything PypeIt offers here is unit-aware.** Zeropoints are AB mag for
  e-/s/Å, and throughput is the end-to-end fraction, so the ETC core can reuse
  `core/flux_calib.py` directly rather than reimplementing it.

Open questions are collected in the Q&A section. As instructed, I edited no
code for this task. No git commands were run other than read-only ones.

### 2026-09-29 (Acted on Q&A answers)

Read the answers to the Q&A and recorded the decisions in a new
`## Project decisions` section of `CLAUDE.md`, so that later prompt docs
inherit them:
- First targets are MOSFIRE J, LRIS-B 600/4000 and LRIS-R 600/7500.
- Throughputs are built from scratch from our own standard-star reductions;
  the archived sensfuncs are not used.
- Raw data come from KOA, in a separate prompt doc.
- Optical sky comes from our own frames, NIR sky from the Gemini Maunakea
  models.
- A Python library now, shaped for a later WMKO-hosted web front end.
- Existing Keck ETCs are a sanity check only.
- Verified PypeIt defects are fixed in PypeIt.

This supersedes the build order in the Report (DEIMOS first). I left the Report
as written, as a record.

Q&A #7: checked the items against the PypeIt source.
- **`keck_nirspec_high_old` dark current is a confirmed bug.**
  `keck_nirspec.py:595` sets `darkcurr = 0.8` and comments it as "e-/s/pixel".
  But `DetectorContainer` (`images/detector_container.py:66`) defines
  `darkcurr` in e-/pixel/hour, so the value is 3600x too low. It should be
  2880, which the commented-out block at `keck_nirspec.py:1507` already gives.
  This needs a one-line PypeIt fix; I did not edit PypeIt, since that repo
  and its branches are yours.
- **The MOSFIRE `saturation = 1e9` is not a bug.** It is a deliberate hack
  ("ADU, this is hacked for now", `keck_mosfire.py:66`) so that the reduction
  does not mask bright flats. PypeIt should keep it. The MOSFIRE ETC needs the
  true full-well / linearity limit, and that belongs in this repo's instrument
  config.
- **The NIRES `saturation = 1e6` is an explicit guess.** It is not needed for
  the current targets.

Things to carry into the KOA / build prompt doc:
- **LRIS-R detector era.** PypeIt has 600/7500 arc templates and dev-suite
  files for `keck_lris_red` and `keck_lris_red_orig`, but **not** for
  `keck_lris_red_mark4`, the current detector. An ETC for present-day LRIS-R
  600/7500 needs mark4 standards from KOA, and probably a mark4 600/7500
  wavelength template in PypeIt.
- **LRIS-B 600/4000.** It is well covered in the dev suite (`long`, `multi`,
  `slitless` and `orig` setups). The dichroic (d560 vs d680) affects
  throughput, so it has to be an ETC parameter.
- **MOSFIRE J.** The dev suite has `keck_mosfire_j_multi` and
  `keck_mosfire_j2_long`, and only J2_long has a standard (LDS749B). J-band
  standards (ideally A0V telluric stars as well as spectrophotometric ones)
  will have to come from KOA.

Housekeeping: you ran `pip install -e .`, and the prompt doc keeps its name.
The `python:*` allow entry in `.claude/settings.json` is unchanged, since that
question was not answered. As instructed, I asked no new questions. No git
commands were run.
