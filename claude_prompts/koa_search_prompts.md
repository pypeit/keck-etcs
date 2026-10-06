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

### MOSFIRE prompt 1 (2026-10-05)

1. **Lamp arcs: which to download in prompt 2 (design D44)?**
   - 74 of the 372 candidate nights (19.9 percent) have Ne/Ar lamp arcs
     matching the standard's mask and filter.
   - Separately, PypeIt wavelength-calibrates `long2pos_specphot` on those
     arcs, not on OH lines. So for specphot nights they are **required for
     the reduction**, not just optional input for the monitor. Specphot
     carries 51 of the 62 wide-slit standard rows.

   The options:
   - (a) arcs for specphot nights only;
   - (b) (a) plus matching arcs on every downloaded night, for the
     monitor's lamp-line metrics (a few frames per night).

   *Default:* (b).
   >Answer: (b).

2. **A1V and other non-A0V telluric stars.** 168 rows (128 nights, 81
   stars) are HIP/HD stars that are not A0 dwarfs in SIMBAD: mostly A1V
   (e.g. HIP 56736, 22 rows), Am (HIP 87643), A2III/IV, F3V, or untyped. N3's
   Vega model is for A0V, so they are `other` and unusable. Only 11 of them
   are wide-slit nights with flats.

   *Default:* leave them out (A0V only, as N3 says). Revisit if the
   sample proves too small.
   >Answer: Your default

3. **The 5" slit question for Josh Walawender (design 8).** The census
   answers it from the data:
   - of the 62 wide-slit standard rows, 51 are `long2pos_specphot` (13
     "(align)"), 9 are `LONGSLIT-46x5` and 2 are 10" slits;
   - the 46x5 nights are nearly all the Hennawi program (LDS749B 2022;
     GD153 on 2024-12-29/30, 2025-01-25, 2025-07-18/22/23).

   So the 5" long slit was not routine; long2pos_specphot is the standard
   wide-slit mode, as design 4.1 anticipated.

   *Default:* record this in the design and drop the question to WMKO,
   unless you still want to ask.
   >Answer: Your default

4. **The pilot nights** (`nautilus/manifests/nights_pilot.csv`, rules in
   `make_night_manifest.py`):

   | Night | Standard | Class | Mask | Band | Role |
   |---|---|---|---|---|---|
   | 20241230 | GD153 | WD | LONGSLIT-46x5 | J2 | WD on the dry-run path, another night |
   | 20170615 | HD133772 | A0V | long2pos_specphot | J | A0V, 12 lamp arcs |
   | 20240721 | Feige110 | WD | long2pos_specphot | J | WD on the same mask, band and era as the A0V |
   | 20131225 | BD+17 4708 | archive (CALSPEC sdF8) | LONGSLIT-3x4 | J | era 2012-16 |
   | 20250722 | GD153 | WD | LONGSLIT-46x5 | J2 | era 2025-04.. |

   *Default:* download and reduce these in prompt 2 and S15a.
   >Answer: Your default

### MOSFIRE prompt 2 (2026-10-05)

1. **Go-ahead for batch 1 (in-cluster).** The probe passed, so the
   downloads run as `nautilus/koa_download_job.yaml` over
   `nautilus/manifests/nights_batch1.csv`:
   - 19 reducible public wide-slit nights, including the 5 pilot nights;
   - about 620 frames, at most about 10.5 GB;
   - `parallelism` 2, `--lamp-arcs`.

   The steps:
   - (a) commit (the script is new and the image must contain it);
   - (b) rebuild and push the image, `bash nautilus/build_image.sh --push`
     (tag **0.2.0**: `keck_etcs.__version__` is bumped; same pin 8017f47).
     This build also carries S8's filter curves, S15a's A0V and long2pos
     code and the driver fixes below;
   - (c) I set the digest in `koa_download_job.yaml`, create the ConfigMap,
     set `completions: 19` and apply the Job.

   *Default:* yes to (c) once you have done (a) and (b). One night,
   20240721, is already on S3 from my `--to-s3` test, and the Job will skip
   it.
   >A. I have done (a) and (b).  (c) is yours


2. **Two pilot nights changed** after you approved the list. Both were
   unreducible, which I found here:
   - 20250722 has no narrow-slit OH frames in J2 → **20250723** (same
     star, same era, 36 frames of 150 s);
   - 20131225 (BD+17 4708) has only 1.5 s OH frames → **20140601**
     (Feige110, long2pos_specphot with 2 arcs, era 2012-16).

   *Default:* accept.
   >Answer: Your default

3. **Unreducible wide-slit nights: 28 long2pos_specphot rows** have no
   long2pos arcs that night, and 3 LONGSLIT ones have no OH frames of 55 s
   or more. Possible later options:
   - arcs from an adjacent night with the same mask and filter;
   - the OH lines in the narrow long2pos slits;
   - accepting shorter OH frames.

   *Default:* leave them out of batch 1. Revisit in S15b if the
   reducible sample (20 nights, 13 stars) proves too small for the era
   medians.
   >Answer: Your default

### MOSFIRE prompt 3 (2026-10-05)

1. **Rebuild the image before any reduction (0.2.1).**
   - Today's driver changes are not in 0.2.0, which was built from 8ab7cb9:
     - a science frame without an extracted object no longer fails the
       night (a faint validation quasar must not cost the standard's
       sensfunc);
     - only the frames listed in `raw/manifest.ecsv` are used.
   - The downloader's spectroscopy-only and validation-science selection
     is also newer than 0.2.0.
   - `keck_etcs.__version__` is bumped to **0.2.1**.

   *Default:* you commit, then run `bash nautilus/build_image.sh --push`
   (or build plus the one-line `docker push` as before) and paste the
   digest. I then point `night_job.yaml` (and the download job) at 0.2.1
   for the S15a pilot.

>A. Done

2. **Strays in the bucket** (small, harmless):
   - `mosfire/20241229/raw/m241229_0209.fits`, the imaging-mode
     acquisition frame (MF.20241229.41741.74) that the first validation
     pass picked up before the spectroscopy filter. It is no longer in the
     night's manifest, and the driver ignores unlisted frames.
   - My test status rows under `runs/local-download-test/`,
     `runs/koa-validation-local/` and `runs/koa-refresh-local/`.
   - `s3_sync.py` has no delete.

   *Default:* leave them. Or delete them yourself with
   `aws --profile default --endpoint-url https://s3-west.nrp-nautilus.io s3 rm s3://keck-etcs/<key>`.
>A. Use your default

3. **More validation points?** 4 program nights have science frames but
   no reducible same-night standard: 20191119 (no standard), 20200529
   (Feige110 narrow), 20201025 (GD71 narrow) and 20250108 (GD153, no flats
   or calibrator). They could be validated against the era-median
   throughput instead of a same-night sensfunc.

   *Default:* not now. Design 6.1 uses the same night's standard; revisit
   after S16 if more points are wanted.
>Answer: Your default

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs

### 2026-10-05 (MOSFIRE prompt 1: census, candidate table, SAMPMODE census, night manifests)

**Tools:** `pykoa`, `astroquery` and `pyvo` are not in `pypeit14b`.
Nothing was installed: every query uses plain HTTP TAP via `requests`.
- KOA: `https://koa.ipac.caltech.edu/TAP/sync`, table `koa_mosfire`.
- SIMBAD: `/simbad/sim-tap/sync`.
- VizieR: `tapvizier.cds.unistra.fr`, table `II/246/out`.

Raw answers are cached under `$KECK_ETCS_DATA/koa/` (local).

**Learned about KOA:**

- **KOA TAP returns public frames only.** Anonymous queries are rewritten
  with `current_date > add_months(date_obs, propint)` (seen in an error
  message), so every candidate is public by construction (`propint`: 18
  months for 12,000 frames; 0, 6, 12 or 24 for the rest).
- `date_obs` cannot be compared to a string (Oracle ORA-01861); select a
  night by `koaid LIKE 'MF.YYYYMMDD%'`.
- **KOA's CSV does not escape quotes** in text fields (`object = dome flat:
  longslit, 120" x 0.7"`), so the census reads KOA as VOTable.
- **`koaimtyp` is unreliable for MOSFIRE.** On 2022-04-09 the J0841 and
  LDS749 frames and the five lamp-off dome flats are all `flatlamp`
  (`FLATSPEC = 1`, as in the headers).
- KOA has no `FLAMP1`/`FLAMP2`; `flimagin`/`flspectr` are other controls,
  mostly off or empty. Lamp-on and lamp-off flats therefore cannot be told
  apart from KOA; the driver checks the headers.
- The census classes: on-sky = `axestat` tracking or slewing and not a FLAT
  target; dome flat = not on sky and a FLAT target or KOA flat type; lamp
  arc = `pwstata7/8 = 1`.
- Every column the doc lists exists. `propint` is the proprietary period;
  `pwloca7/8` name the Ne/Ar outlets.

**`scripts/koa/search_mosfire_standards.py`:**

- KOA query: `gratmode = 'spectroscopy'`, J/J2/J3, LONGSLIT% or
  long2pos%. That gives **12,769 public frames**: on sky 5,301, dome flats
  6,187, lamp arcs 1,138, other 143.
- Standards:
  - **archive:** within 60" of a star in PypeIt's 7 archives (242 stars),
    giving `WD` (type D*, or a blackbody DC) or `archive` (non-WD CALSPEC
    stars PypeIt fluxes: HD116405 and HD172728 (A0V), BD+17 4708, HZ44,
    BD+75 325, P330E);
  - **A0V:** within 60" of a SIMBAD A0 dwarf with V < 11 (one all-sky
    query: 25,935 A0 stars, of which 24,803 are dwarfs or unclassified),
    with 2MASS J from VizieR (5" cone, cached);
  - **other:** a HIP/HD target that is neither.
- **The `archive` class is a fourth class** beyond the doc's WD/A0V/other:
  without it, usable CALSPEC stars would have been lost in "other". The
  driver treats WD and archive alike.
- **The match radius is checked.** Separations are bimodal: 0-20" (the
  long slit) and 45-56" (the off-centre long2pos slits). There are no
  archive matches beyond 56", and only 4 of 2,576 A0-dwarf frames fall
  between 60" and 180". PypeIt's 20' tolerance is far too loose for a
  census.
- **The unmatched HIP stars are not A0V:** HIP 56736 A1V, HIP 87643
  kA1hA2mA3, HIP 24311 A2III/IV, HIP 38490 A1V, HIP 49180 F3V; HIP 106329
  and HIP 24508 have no type.
- Night = the UT date of (UT + 6 h), 08:00 to 08:00 HST. It keeps
  afternoon flats with their night (a test checks 23:30 UT → the next
  date).
- `slit_length_bars` holds the CSU bar count, as the harvest's
  `slit_length` does. I first wrote a function that claimed arcsec but
  returned bars.

**Results** (`keck_etcs/data/mosfire/koa_standards_candidates.ecsv`, one
row per night × standard × mask × filter; registered in `index.yaml`):

- **594 rows over 372 nights:**

  | Class | Rows | Nights | Stars |
  |---|---|---|---|
  | WD | 31 | 26 | 5 (GD71 12, GD153 10, LDS749B 3, HZ4 3, Feige110 3) |
  | archive | 20 | 18 | 7 |
  | A0V | 375 | 273 | 102 (V 5.1-10.2; every one has 2MASS J) |
  | other | 168 | 128 | 81 |

- **Per era and slit class** (all classes; "usable" = WD, archive or A0V
  with flats):

  | Era | Wide | Narrow | Wide usable | Narrow usable |
  |---|---|---|---|---|
  | 2012-04..2016-09 | 24 | 322 | 14 | 155 |
  | 2017-02..2025-02 | 51 | 192 | 35 | 109 |
  | 2025-04.. | 3 | 2 | 3 | 1 |

- **Public wide-slit usable standards with flats: 52 rows, 44 nights, 27
  stars** (WD 10, archive 1, A0V 41), across all three eras. That is above
  the milestone's ">= 10 standards over >= 2 eras", so the WMKO question
  is not blocking. The narrow-slit sample (265 usable rows) is for the slit
  loss.
- Wide masks: `long2pos_specphot` 38 and its "(align)" variant 13,
  `LONGSLIT-46x5` 9, 10" slits 2. **long2pos_specphot dominates** (Q&A 3),
  so S15a's long2pos branch is on the main path.
- **Matching lamp arcs:** 74 of 372 candidate nights (19.9%) (Q&A 1).
- 10 nights are from the priority (Hennawi/Yang/Wang) programs.
- **Check:** 2022-04-09, LDS749B, LONGSLIT-46x5, `wide_slit = True`,
  MF.20220409.55932 and .56084, 11 flats → **PASS**.

**SAMPMODE census** (`keck_etcs/data/mosfire/koa_sampmode_census.ecsv`;
168,038 public on-sky spectroscopy frames):

| Mode | Share |
|---|---|
| MCDS | **84.21%** (MCDS-16 73.29%, MCDS-4 6.06%, MCDS-8 2.04%, MCDS-1 2.15%) |
| CDS | **14.79%** |
| UTR | **0.94%** |
| Single | 0.06% |

UTR is below "a few percent", so by D13 the ETC does not need UTR.

**`scripts/koa/make_night_manifest.py`:**

- Writes `nautilus/manifests/nights_<batch>.csv`: the 7 design columns plus
  `std_class`, `jmag_2mass`, `std_ra`, `std_dec` (S15a-3) and **`filter`**,
  new.
  - Some nights have the standard in both J and J2, and a pod reduces one
    band, so `reduce_standard.py`'s `--filter` now defaults to `$FILTER`.
  - `status_row.py` and `night_failures.py` carry `filter` among their
    optional columns.
- One row per night; `standard` without spaces.
- `check()` parses the manifest as the night job does.
- **`nights_dryrun.csv`** is regenerated: the first 6 columns are
  identical, and the optional columns are added (LDS749B, WD, J2).
- **`nights_pilot.csv`**: 5 nights by fixed rules (Q&A 4). Rule 3 prefers
  era 2 so that the WD (Feige110, 2024-07-21) and the A0V (HD133772,
  2017-06-15) share mask, band and era for S15a's comparison; my first rule
  set picked Feige110 in 2014.

**Tests:** `keck_etcs/tests/test_koa_manifest.py` (4) checks:
- the candidate table has the dry-run night;
- the manifests parse;
- the pilot has 3-5 nights without 2022-04-09, with WD and A0V;
- the night definition, slit parsing and A0-dwarf rule.

The `night_failures` test is updated. The suite has **100 passed**.

**For prompt 2:** download, per night, the standard's frames, the dome
flats (same band; LONGSLIT or long2pos to match), and the lamp arcs (always
for specphot; matching arcs per Q&A 1), from the `koaids` and the night's
calibrations in the cached KOA table.

**Questions:** Q&A MOSFIRE-1 (lamp arcs), 2 (A1V stars), 3 (the 5" slit
question is answered by the data), 4 (pilot nights).

### 2026-10-05 (MOSFIRE prompt 2: KOA probe OK; download script, Job, batch-1 manifest; driver fixes)

**Answers read** (prompt 1):

- (1) **(b)**: specphot nights always get their arcs, and every night gets
  the matching arcs via `--lamp-arcs`.
- (2) A0V only.
- (3) **The 5" slit question is settled by the census and dropped.**
  Design 4.1 and section 8 are updated: the WMKO question is closed, and
  the SAMPMODE census is done (UTR 0.94%).
- (4) Pilot as proposed, but two nights changed (Q&A prompt 2, item 2).

Also done, approved in `keck_mosfire_prompt_5.md` (S15b-1): **the first
real backup**, `backup_products.py --run`, copied 60 files (6.4 MB) to
`AIOcean:keck-etcs/`; `rclone check --one-way` reports 60 match, 0 missing,
0 differ (COMPLETE). A dry run afterwards would copy 0 (idempotent).

**How frames are fetched:**

- `pykoa` is not installed and is not needed. KOA's
  `cgi-bin/getKOA/nph-getKOA?filehand=<filehand>` (the `filehand` column of
  `koa_mosfire`) serves public frames over plain HTTP: 16.9 MB in 1.6 s
  locally.
- KOA also stores the original name (`ofname`, e.g. `m220409_0218.fits`),
  which the downloads keep.
- The KOA copy of MF.20220409.55932 has data **bit-identical** to the
  dev-suite `m220409_0218.fits`. KOA adds header cards (KOAID, PROGID,
  `GUIDFWHM`, IMAGEMN, …), so the sha256 differs.

**Probe** (`nautilus/koa_probe_job.yaml`: one pod, image 0.1.6, standard
library only, no bucket or secret), applied 2026-10-05 23:32 UTC:
- **PROBE OK**;
- TAP answered in 3.8 s; the 16,856,640-byte frame downloaded in 1.5 s
  (10.9 MB/s), FITS, sha256 aa2fe1eb… (the same as locally);
- **pods reach KOA anonymously, so downloads run in-cluster** and the D37
  fallback is not needed;
- the admission webhook warned about limit/request ratios above 1.2, so
  requests now equal limits in both KOA manifests.

**`scripts/koa/download_mosfire_night.py`** (standard library plus
astropy, so it runs in the image):

- Per night (a manifest row, or a night via the candidate table) it queries
  KOA for the night's frames (UT date of UT + 6 h) and selects:
  - **standard**: on sky, the filter and mask, within 60";
  - **dome_flat**: one mask only (the standard's, else the OH frames',
    else the most common of the right kind), so that PypeIt does not trace
    mixed slit widths;
  - **oh_arc** (LONGSLIT): up to 6 narrow-slit on-sky frames of **at least
    55 s**, nearest in time;
  - **lamp_arc**: long2pos arcs for specphot (required), plus the arcs on
    the standard's mask with `--lamp-arcs`.
- `no standard` (exit 11) and `no calibs` (no flats, or no calibrator;
  exit 10) download nothing.
- It writes `raw/manifest.ecsv` (koaid, file, frame_type, target, slit,
  filter, sampmode, numreads, exptime, airmass, ut, mjd, size, sha256,
  progid, priority).
- **Idempotent:** a frame in the manifest with the same size on disk, or
  in the bucket with `--to-s3`, is not fetched again.
- `--to-s3` pushes `mosfire/<night>/raw/` and checks the bucket sizes
  against the manifest.
- Status rows go to `runs/<job>/download_status/<idx>_<night>.ecsv`;
  `--collect` builds `download_status.ecsv`.

**Tests** (scratchpad, plus one night into the bucket):

- **20131225 local**: 22 frames (4 standard, 12 flats, 6 OH), 371 MB; the
  re-run downloaded 0.
- **20250722**: `no calibs` (2 standard frames, 20 flats, 0 OH frames),
  nothing downloaded.
- **20240721 `--to-s3`** (batch-1 index 14): 26 frames (7 standard, 13
  flats, 6 arcs), 438 MB in `s3://keck-etcs/mosfire/20240721/raw/`; sizes
  match the manifest.
  - A re-run from **empty scratch** downloaded 0 (26 skipped, using the
    bucket sizes alone).
  - My test status rows are left under `runs/local-download-test/` in the
    bucket (2 small files).

**Problems found by running the driver on a KOA night** (fixed in
`scripts/mosfire/reduce_standard.py`):

1. **2013 headers have no `FLAMP1`/`FLAMP2`**, so "no lamp-on flats"
   resulted. `FLATSPEC` is reliable then, so the driver now falls back to
   `FLATSPEC == 1` off sky when the FLAMP cards are absent. (In 2022,
   `FLATSPEC = 1` even on sky; the FLAMP cards exist there and win.)
2. **Duplicate rows:** `pypeit_setup` lists calibration frames shared by
   several setups in each of them, so the merged PypeIt file had every
   flat twice. Rows are now kept once per file (a note records it).
3. **OH frames typed science** would fail `no trace` on faint unrelated
   targets. The driver now reads `raw/manifest.ecsv`: `oh_arc` →
   `arc,tilt` and `standard` → `standard`.

- After the fixes, `--setup-only` on 20131225 gives 22 rows: 12 pixelflats,
  4 standards (pairs 24↔25, 26↔27) and 6 `arc,tilt`.
- 2022-04-09's PypeIt data table is still **identical** to the pod's.
- Tests: the FLATSPEC fallback and `raw_manifest_types`; the suite has
  **102 passed**.

**Census refined** (`search_mosfire_standards.py`):

- New columns `n_oh_frames` (≥ 55 s), `n_l2p_arcs`, `wavecal` (oh, lamp or
  none) and `reducible`.
- **Reducible public wide-slit: 20 nights, 13 stars** (oh 5, lamp 15; era
  1: 7, era 2: 12, era 3: 1), out of 52 usable rows. The losses: **28
  specphot rows without long2pos arcs** (PypeIt calibrates that mask on
  arcs, since the standard frames are too short for OH), and LONGSLIT
  nights whose narrow frames are short telluric exposures (most of 2012-16).
- The pilot now requires reducible nights (Q&A prompt 2, item 2), and
  design 4.1 records it.

**Manifests and YAML:**

- `nautilus/manifests/nights_batch1.csv` (`make_night_manifest.py batch1`):
  the 19 reducible wide-slit nights except 2022-04-09, which is already on
  S3. They are the pilot 5 plus 14 more: 13 A0V and 2 Feige110 nights on
  long2pos_specphot, and 4 GD153 nights on LONGSLIT-46x5. No further
  reducible priority-program night was available. About 620 frames, at
  most 10.5 GB.
- `nautilus/koa_download_job.yaml`:
  - Indexed, `parallelism` 2, `backoffLimit` 4, `activeDeadlineSeconds`
    14400, 1 CPU / 2 Gi / 20 Gi scratch;
  - the credentials secret mounted; `--to-s3 --lamp-arcs`;
  - data outcomes (exit 10/11) end the pod successfully, other failures
    retry;
  - image **0.2.0**, which does not exist yet (the script is not in 0.1.6).
- `nautilus/validate_manifests.py` gains per-file rules (the probe touches
  no bucket; the download job needs credentials and scratch; the reduction
  jobs also need the S4b env): MANIFESTS OK.
- `nautilus/Dockerfile`'s image check adds
  `download_mosfire_night.py --help`.
- `keck_etcs.__version__` → **0.2.0**.

**Verify (prompt 2):**

- The probe result is logged before any batch.
- Flats and a standard in every downloaded manifest, `s3_sync.py ls` sizes
  matching the manifest, and re-runs downloading nothing: checked on the
  test nights. A night without calibrators is recorded `no calibs`.
- Total sizes: 371 MB and 438 MB for the test nights; batch 1 is estimated
  at ≤ 10.5 GB.
- **Batch 1 itself waits** for the 0.2.0 image and your go-ahead (Q&A
  prompt 2, item 1).

**Housekeeping:** `$CLAUDE_JOB_DIR` was unset in this shell, so some
scratch files went to the shared `/tmp`. I moved or removed only my own
(listed by name and time); later work uses the session scratchpad.

### 2026-10-05 (MOSFIRE prompt 3: validation targets, spec2d manifests, downloads; batch 1 complete)

**Answers read** (prompt 2): you did (a) the commit and (b) the build, and
(c) applying the Job was mine; defaults for the pilot changes and the
unreducible nights.
- **The 0.2.0 tag was not in the registry**: the build had run but not the
  push (`docker manifest inspect` found no `:0.2.0`, and `:latest` still had
  0.1.6's digest).
- You pushed it with `DOCKER_CONFIG=~/.docker-keck-etcs docker push …:0.2.0`:
  digest **sha256:aa538854d3b807696821f1df89bafff31ee325176576d60663df1ed7f291d978**
  (keck-etcs 8ab7cb9, PypeIt pin 8017f47, from the image's
  `KECK_ETCS_GIT_SHAS`).

**Batch 1** (`keck-etcs-koa-download`, `completions` 19, `parallelism` 2,
image 0.2.0 with the digest set in the YAML; ConfigMap
`keck-etcs-koa-nights` from `nights_batch1.csv`):
- **19 of 19 succeeded:** 18 `success` and 1 `skipped` (20240721, already
  on S3 from my test).
- 8.56 GB in the manifests, 8.12 GB downloaded; 9-73 s per pod (about
  10 MB/s).
- Every night has its standard and dome flats, plus long2pos arcs (2-12)
  or 6 OH frames.
- The status table is `runs/keck-etcs-koa-download/download_status.ecsv`.

**`scripts/koa/find_validation_targets.py`** →
`keck_etcs/data/mosfire/koa_validation_targets.ecsv` (registered):

- It lists the Hennawi/Yang/Wang (D9) science exposures on narrow J/J2/J3
  long slits (≥ 55 s, not a standard), per night × target × filter × mask,
  with the same-night standard in that filter. A target is a validation
  point when that standard is reducible.
- **9 targets on 9 nights, all Hennawi; 5 validation points:**

  | Night | Target | Band | Exposures | Standard |
  |---|---|---|---|---|
  | 20220409 | J0841+3814_OFF | J2 | 4 × 150 s | LDS749B |
  | 20241229 | rJ0933+7427 | J | 5 × 150 s | GD153 |
  | 20241230 | J0942+6448YJ2 | J2 | 16 × 150 s | GD153 |
  | 20250125 | J1004+6844 | J2 | 24 × 150 s | GD153 |
  | 20250723 | J1629+6831 | J2 | 36 × 150 s | GD153 |

  The other four nights (20191119, 20200529, 20201025, 20250108) lack a
  reducible same-night standard (Q&A prompt 3, item 3).
- **`nautilus/manifests/nights_validation.csv`**: the 4 new nights, each
  the standard's row with `spec2d = 1`. **`spec2d = 1`** is now also set for
  them in `nights_batch1.csv` (4 rows) and `nights_pilot.csv` (20241230,
  20250723). 2022-04-09 keeps its dry-run row (already `spec2d = 1`).

**Downloader:**

- On validation nights (manifest `spec2d = 1`) it now takes **every**
  priority-program science exposure of the filter as `science`. These also
  serve as the OH arcs, so no separate `oh_arc` frames are picked.
- **Bug found and fixed:** KOA labels some on-slit acquisition exposures
  `gratmode = 'imaging'` (MF.20241229.41741.74, 150 s on
  LONGSLIT-46x1 (align)). The census queries spectroscopy only, but the
  per-night query had no filter, so the first validation pass picked the
  frame as "science".
  - The per-night query is now `gratmode = 'spectroscopy'`.
  - A refresh over all 19 nights gives identical selections except
    20241229 (science 6 → 5) and downloads nothing.
  - The stray object stays on S3, and the driver ignores it (below).
- The validation pass (local `--to-s3`, since 0.2.0 predates the selection)
  added 58 science frames (0.98 GB). The validation nights now hold 5 / 16
  / 24 / 36 science frames.

**Driver** (`reduce_standard.py`, not yet in an image; Q&A prompt 3,
item 1):
- With a `raw/manifest.ecsv`, only the frames it lists are used (a note
  names any ignored frame).
- **`no trace` now applies to standard frames only.** A science frame
  without an extracted object is recorded in
  `run_manifest.json['science_without_objects']` with a warning, since the
  quasars are faint and the night must not lose its sensfunc; `spec2d` is
  kept for the validation step.

**`scripts/koa/verify_raw_on_s3.py`** (read-only on the bucket): for each
night of the given manifests it pulls `raw/manifest.ecsv`, lists the
bucket, compares sizes, counts frame types, and requires a standard and
dome flats (plus `science` on `spec2d = 1` nights).
- Result over `nights_batch1.csv` and `nights_validation.csv`: **19 nights,
  9.52 GB, ALL OK**: every frame present at the manifest size.
- Every validation night has both science frames and a same-night
  standard on S3; 2022-04-09 has them from the dry run.

**Tests:** `test_koa_manifest.py` gains a validation test (2022-04-09 is a
validation point; `nights_validation.csv` parses with `spec2d = 1`; batch 1
and the pilot have `spec2d = 1` exactly on the validation nights).
**103 passed.**

**Other:**
- `keck_etcs.__version__` → **0.2.1** for the rebuild.
- Scratch now lives in the session scratchpad.
- **Verify (prompt 3):** validation nights have science frames and a
  standard on S3 (checked above); the manifests carry `spec2d = 1`
  (tested); the downloads used the fallback path, as the prompt allows.
