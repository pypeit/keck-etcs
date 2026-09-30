# KOA search prompts

## Goals

Find, catalogue and download the raw Keck data that the ETCs need from the
Keck Observatory Archive (KOA, koa.ipac.caltech.edu): standard stars for
throughput, plus science frames for validation. This doc starts with
MOSFIRE J-band standards (step S14 of `docs/keck_mosfire_implementation.md`)
and will grow a section per instrument (LRIS 600/4000 and 600/7500 next).
Project decisions (CLAUDE.md): raw data come from KOA; throughputs are built
from standards we reduce ourselves.

Run order: the MOSFIRE section can start at any time, in parallel with
`claude_prompts/keck_mosfire/keck_mosfire_prompt_1.md`. Its outputs are
required by `keck_mosfire_prompt_5.md`. Downloads need the data root from
`keck_mosfire_prompt_1.md` step S1 (create it if it does not exist yet).

## Context

- Design: `docs/keck_mosfire_design.md`, sections 2 (D2-D4, D6, D9, D13,
  N3, N8), 4.1 (selection criteria and the fields to record), 4.2 (data
  root), 8 (open items: the 5" slit question for Josh Walawender; the
  `SAMPMODE` census).
- Plan: `docs/keck_mosfire_implementation.md`, step S14.
- KOA: `https://koa.ipac.caltech.edu`; programmatic access through the KOA
  TAP service and the `pykoa` package (check whether it is installed in
  `pypeit14`; install into that environment only if the user agrees). MOSFIRE
  metadata columns of interest: `koaid`, `date_obs`, `ut`, `targname`,
  `object`, `ra`, `dec`, `maskname`, `filter`, `gratmode` / `obsmode`,
  `sampmode`, `numreads`, `truitime`, `airmass`, `pattern`, `frameid`,
  `yoffset`, `progid`, `progpi`, `koaimtyp`, and the proprietary-period flag
  (Keck data become public 18 months after observation). Confirm the exact
  column names against the KOA MOSFIRE table description.
- Standard lists: PypeIt's `pypeit/data/standards/calspec/calspec_info.txt`
  (name, RA, Dec, V, type), `xshooter/xshooter_info.txt`, `esofil_info.txt`;
  A0V stars via SIMBAD (astroquery) for any `targname` matching `HIP`, `HD`
  or a SIMBAD spectral type A0V within 20 arcmin of the pointing; 2MASS J
  and its error via VizieR (II/246). The 2022-04-09 LDS749B frames
  (m220409_0218-0219, LONGSLIT-46x5, J2) must appear in the results as a
  check.
- Selection (design 4.1): `maskname LIKE 'LONGSLIT%'` or `long2pos%`,
  `filter` in {J, J2, J3}, spectroscopy mode; classify slit width from the
  mask name (`LONGSLIT-46x5` is 5"; `long2pos_specphot` has a wide slit);
  standards on slits >= 3" form the throughput sample, narrower ones the
  slit-loss sample. Priority nights: the Hennawi/Yang/Wang high-redshift
  quasar program (J-band long slit, 2019-2023) for validation and their
  standards.
- Data root: `$KECK_ETCS_DATA/mosfire/<YYYYMMDD>/raw/`, default
  `/Users/xavier/Projects/PypeIt/keck-etcs-data`; nothing there is committed.
  A night needs its dome flats (lamp on and off) as well as the standard.
- Rules (CLAUDE.md): the user runs git; `conda run -n pypeit14`; every
  query and download is a script on disk under `scripts/koa/`; log each
  prompt here.

## Prompts

### MOSFIRE

1. **Census and candidate table.** Write
   `scripts/koa/search_mosfire_standards.py` that queries KOA for all
   MOSFIRE spectroscopy in J, J2 and J3 on long slits and long2pos masks
   (2012-04 to now), matches targets to the CALSPEC/X-shooter lists and to
   SIMBAD A0V stars, fetches 2MASS J for the A0V stars, and writes
   `keck_etcs/data/mosfire/koa_standards_candidates.ecsv` with the fields of
   design 4.1 plus `std_class` (WD, A0V, other), `slit_width_arcsec`,
   `wide_slit` (>= 3"), `era` (design D6), `public` (proprietary period
   over), and `has_flats` (dome flats on the same night). From the same
   query, write the `SAMPMODE` and `NUMREADS` histogram of all MOSFIRE
   science frames (not just standards) to
   `keck_etcs/data/mosfire/koa_sampmode_census.ecsv`; this decides whether
   the ETC needs UTR (design D13). Verify: the LDS749B 2022-04-09 frames
   appear with `wide_slit = True`; the number of public wide-slit standards
   per era is reported, and if it is below 10 in total, say so explicitly
   against the open question to Josh Walawender (WMKO) about whether the 5"
   slit was ever routine. Risks: KOA column names and TAP quirks;
   `astroquery`/`pykoa` availability in `pypeit14`; SIMBAD rate limits. Log
   your work, with the counts per era and slit class and the `SAMPMODE`
   percentages.

2. **First download batch.** Write `scripts/koa/download_mosfire_night.py`
   that, for a list of nights, downloads the standard frames, the science
   frames of interest (for the quasar-program nights) and the night's dome
   flats into `$KECK_ETCS_DATA/mosfire/<YYYYMMDD>/raw/`, records a manifest
   (`raw/manifest.ecsv` with koaid, file, frame type, target, slit,
   `SAMPMODE`, `NUMREADS`, exptime, airmass), and skips files already
   present. Choose the first batch: all public wide-slit standards, then the
   Hennawi/Yang/Wang nights, up to about 20 nights. Verify: every downloaded
   night has flats and a standard in the manifest; total size reported;
   `git status` shows only the two scripts. Risk: KOA login for proprietary
   data is out of scope; only public data. Log your work with the batch
   list.

3. **Validation science frames.** Extend the candidate table with the
   quasar-program science exposures (target, date, exposure count, slit)
   that can serve as S/N validation points (design 6.1), and download those
   not already fetched in prompt 2. Verify: each validation night has both
   science frames and a same-night standard; the list is written to
   `keck_etcs/data/mosfire/koa_validation_targets.ecsv`. Log your work.

### LRIS

(To be written when the LRIS ETC starts: 600/4000 grism with d560 and d680,
600/7500 grating on the mark4 detector.)

## Q&A

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs
