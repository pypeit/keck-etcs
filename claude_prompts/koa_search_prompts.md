# KOA search prompts

## Goals

Find, catalogue and download the raw Keck data that the ETCs need from the
Keck Observatory Archive (KOA, koa.ipac.caltech.edu): standard stars for
throughput, plus science frames for validation. This doc starts with
MOSFIRE J-band standards (steps S14 and S14b of
`docs/keck_mosfire_implementation.md`, v0.3) and will grow a section per
instrument (LRIS 600/4000 and 600/7500 next). Project decisions (CLAUDE.md
and design D30, D32, D37): raw data come from KOA; throughputs are built
from standards we reduce ourselves; the metadata search runs locally; the
raw-frame downloads run as a Nautilus Job that writes straight to the
private S3 bucket `s3://keck-etcs`, with a local download and push as the
fallback; only public data are fetched.

Run order: the MOSFIRE census (prompt 1) can start at any time, in parallel
with `claude_prompts/keck_mosfire/keck_mosfire_prompt_1.md`. The download
prompts (2, 3) need part 1's S1b (bucket access, `s3_sync.py`, the
credentials secret) and part 2's S4a (the image, with `pykoa` in it) for
the in-cluster path; the fallback needs only S1b. The outputs are required
by `keck_mosfire_prompt_5.md`.

## Context

- Design: `docs/keck_mosfire_design.md` (v0.3), sections 2 (D2-D4, D6, D9,
  D13, D32, D33, D37, N3, N8), 4.1 (selection criteria and the fields to
  record), 4.2 (S3 layout: `mosfire/<YYYYMMDD>/raw/*.fits` plus
  `raw/manifest.ecsv`), 4.8.4 (night-manifest columns), 8 (open items: the
  5" slit question for Josh Walawender; the `SAMPMODE` census; KOA
  reachability from pods).
- Plan: `docs/keck_mosfire_implementation.md` (v0.3), steps S14 and S14b.
- KOA: `https://koa.ipac.caltech.edu`; programmatic access through the KOA
  TAP service and the `pykoa` package (check whether it is installed in
  `pypeit14`; install into that environment only if the user agrees; add it
  to `requirements.txt` so the image gets it). MOSFIRE metadata columns of
  interest: `koaid`, `date_obs`, `ut`, `targname`, `object`, `ra`, `dec`,
  `maskname`, `filter`, `gratmode` / `obsmode`, `sampmode`, `numreads`,
  `truitime`, `airmass`, `pattern`, `frameid`, `yoffset`, `progid`, `progpi`,
  `koaimtyp`, and the proprietary-period flag (Keck data become public 18
  months after observation). Confirm the exact column names against the KOA
  MOSFIRE table description.
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
- Storage: the private bucket `s3://keck-etcs` (endpoint
  `https://s3-west.nrp-nautilus.io`; in-cluster
  `http://rook-ceph-rgw-nautiluss3.rook`), prefix
  `mosfire/<YYYYMMDD>/raw/`; local mirror `$KECK_ETCS_DATA/mosfire/<YYYYMMDD>/raw/`
  (default root `/Users/xavier/Projects/PypeIt/keck-etcs-data`; nothing
  there is committed). Every access needs the user's keys: locally the AWS
  profile used by `scripts/nautilus/s3_sync.py`, in pods the secret
  `KECK_ETCS_S3_SECRET` (namespace `pypeit`) settled in
  `keck_mosfire_prompt_1.md` prompt 4. A night needs its dome flats (lamp
  on and off) as well as the standard. Raw frames are not in the backup set
  (design D39): they are re-downloadable from KOA.
- Nautilus conventions for the download Job: design 4.8.1 and the models
  `Oceanography/python/PAB/nautilus/v2_ingest_job.yaml` (two-pass
  idempotent ingest with a failure list) and `v2_ingest_failures.py`;
  `nautilus/night_job.yaml` from `keck_mosfire_prompt_2.md` prompt 6 for
  the Indexed-Job skeleton.
- Rules (CLAUDE.md): the user runs git; `conda run -n pypeit14`; every
  query and download is a script on disk under `scripts/koa/`; no secret
  value in the repo or a log; Job launches are confirmed with the user; log
  each prompt here.

## Prompts

### MOSFIRE

1. **Census, candidate table and night manifests.** Write
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
   the ETC needs UTR (design D13). Also count Ne/Ar lamp frames per
   candidate night (design D44; the calibration monitor of 4.9): MOSFIRE
   frames with `PWSTATA7` or `PWSTATA8` = 1 (the Neon and Argon outlets,
   named in `PWLOCA7`/`PWLOCA8`), matched to the standard's `MASKNAME` and
   filter, plus any `long2pos_specphot` arcs. Add the columns
   `n_lamp_arcs` and `lamp_arcs_match` to the candidate table, and report
   the fraction of candidate nights with matching lamp arcs. The user
   decides from that number whether prompt 2 downloads them. Also write
   `scripts/koa/make_night_manifest.py` that turns a selection of candidate
   nights into `nautilus/manifests/nights_<batch>.csv` with the columns of
   design 4.8.4 (`night, instrument, s3_prefix, standard, slit, spec2d,
   notes`; `std_class` and 2MASS J in `notes` or as extra columns the
   reduction driver reads), and produce `nights_dryrun.csv` (the 2022-04-09
   night) and `nights_pilot.csv` (3-5 public wide-slit nights with flats).
   Verify: the LDS749B 2022-04-09 frames appear with `wide_slit = True`;
   the number of public wide-slit standards per era is reported, and if it
   is below 10 in total, say so explicitly against the open question to
   Josh Walawender (WMKO) about whether the 5" slit was ever routine; the
   manifests parse with the columns `night_job.yaml` expects. Risks: KOA
   column names and TAP quirks; `astroquery`/`pykoa` availability in
   `pypeit14`; SIMBAD rate limits. Log your work, with the counts per era
   and slit class and the `SAMPMODE` percentages.

2. **First download batch (in-cluster Job, S14b).** First settle the
   reachability question: write `nautilus/koa_probe_job.yaml` (namespace
   `pypeit`, the `keck-etcs` image, small resources, `backoffLimit: 0`)
   that runs `pykoa` against one public 2022-04-09 KOA ID and prints
   success or the error; with the user's go-ahead apply it and record the
   result. Then write `scripts/koa/download_mosfire_night.py` that, for one
   night (from a manifest row) or a list of nights, downloads the standard
   frames, the science frames of interest (for the quasar-program nights)
   and the night's dome flats, writes `raw/manifest.ecsv` (koaid, file,
   frame type, target, slit, `SAMPMODE`, `NUMREADS`, exptime, airmass,
   sha256). With `--lamp-arcs`, added only if the user chose it after the
   prompt 1 census, it also fetches the matching Ne/Ar frames as frame type
   `lamp_arc`; only the calibration monitor reads them. With `--to-s3` it
   pushes to `s3://keck-etcs/mosfire/<YYYYMMDD>/raw/`
   through `scripts/nautilus/s3_sync.py`, skipping frames already on S3
   with the same size; without `--to-s3` it writes to
   `$KECK_ETCS_DATA/mosfire/<YYYYMMDD>/raw/`. Write
   `nautilus/koa_download_job.yaml` (Indexed over a night manifest,
   `parallelism: 2` out of politeness to KOA, `activeDeadlineSeconds`, the
   credentials secret mounted, a per-night status row to
   `runs/<job_name>/download_status.ecsv`, header per design 4.8.1). Choose
   the first batch: all public wide-slit standards, then the
   Hennawi/Yang/Wang nights, up to about 20 nights, as
   `nautilus/manifests/nights_batch1.csv`. If the probe succeeded, apply
   the Job with the user's go-ahead; if it failed, run the same script
   locally with `--to-s3` and the user's AWS profile (the design D37
   fallback) and say so. Verify: the probe result is logged before any
   batch; every downloaded night has flats and a standard in its manifest;
   `s3_sync.py ls` sizes match the manifest; total size reported;
   re-applying (or re-running) downloads nothing; a night with no flats is
   recorded `no calibs`; `git status` shows only the scripts, manifests and
   YAML. Risk: KOA login for proprietary data is out of scope; only public
   data. Log your work with the batch list and the probe outcome.

3. **Validation science frames.** Extend the candidate table with the
   quasar-program science exposures (target, date, exposure count, slit)
   that can serve as S/N validation points (design 6.1), write
   `keck_etcs/data/mosfire/koa_validation_targets.ecsv`, mark those nights
   `spec2d = 1` in their manifests (so the reduction pods push `spec2d_*`
   for the validation step), and download those not already fetched in
   prompt 2 by the same in-cluster or fallback path. Verify: each validation
   night has both science frames and a same-night standard on S3; the
   manifests carry `spec2d = 1` for them. Log your work.

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
