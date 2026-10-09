# keck-etcs on Nautilus: operator guide

How the PypeIt reductions behind the keck-etcs calibrations run on the NRP
Nautilus cluster, and how to operate them. The design is in
`docs/keck_mosfire_design.md` (4.8; D30-D39). The work logs are under
`claude_prompts/keck_mosfire/`.

The ETC itself never touches Nautilus or S3: its products ship in git
(`keck_etcs/data/`).

Contents:

1. Namespace, bucket, credentials
2. Bucket layout and the local mirror
3. Image: build and push
4. The PypeIt pin
5. kubectl idioms and the credentials test
6. Reducing a batch of nights
7. Sweeping failures
8. Syncing products back
9. Backup
10. Cutting a calibration release

## 1. Namespace, bucket, credentials

- **Namespace:** `pypeit`; `kubectl` context `nautilus`.
- **Bucket:** `s3://keck-etcs` on Nautilus S3 (Ceph RGW), path-style
  addressing.
  - Endpoint from outside the cluster: `https://s3-west.nrp-nautilus.io`.
  - Endpoint inside it: `http://rook-ceph-rgw-nautiluss3.rook`.
  - Scripts read the endpoint from `ENDPOINT_URL`; `KECK_ETCS_BUCKET`
    overrides the bucket name.
- **The bucket is private** (D32). Only the owner's keys can list, read or
  write it, and anonymous requests get HTTP 403. Nothing in it is shared by
  URL. WMKO and collaborators get the products through the ECSV and FITS
  files committed to git.
- **Local credentials:** an AWS profile holding the Nautilus keys, selected
  with `AWS_PROFILE` (default `default`), or `AWS_ACCESS_KEY_ID` and
  `AWS_SECRET_ACCESS_KEY` in the environment. There is no anonymous
  fallback.
- **In-pod credentials:** a Secret in `pypeit`, mounted, never copied, at
  `/root/.aws/credentials` (`subPath: credentials`), with `HOME=/root`.
  Manifests take its name from `KECK_ETCS_S3_SECRET`:
  - `prp-s3-credentials`, the default: the namespace's existing S3 secret,
    verified to read and write `keck-etcs` (S1b);
  - `keck-etcs-s3-credentials`, the fallback (section 5).
- **No secret value ever appears in this repository,** in a log, or in a
  pod's output. `kubectl get secrets` lists names only; never use `-o yaml`.
- **Widening bucket access** (optional, not done): if WMKO or collaborators
  ever need the S3 products directly, the options are a read policy for
  named users or pre-signed URLs. Not needed while the products ship in git.

## 2. Bucket layout and the local mirror

```
s3://keck-etcs/
  mosfire/<YYYYMMDD>/raw/*.fits, manifest.ecsv     # KOA frames + per-frame manifest (sha256, SAMPMODE, ...)
  mosfire/<YYYYMMDD>/redux/<night>.pypeit           # the pypeit file actually run
  mosfire/<YYYYMMDD>/redux/Calibrations/            # WaveCalib*, Flat*, Edges*, Tilts*
  mosfire/<YYYYMMDD>/redux/Science/spec1d_*.fits    # spec1d always; spec2d only when SPEC2D=1
  mosfire/<YYYYMMDD>/redux/QA/                      # PypeIt QA PNGs
  mosfire/<YYYYMMDD>/sens/                          # sensfuncs (per frame and coadd), telluric QA
  mosfire/<YYYYMMDD>/harvest/                       # <std>_<date>_row.ecsv, <std>_<date>.ecsv, <night>_monitor.ecsv
  mosfire/<YYYYMMDD>/run_manifest.json, run.log, pod.log, gates.json, pypeit_pin_check.json
  manifests/nights_<batch>.csv                      # night manifests that drive the Indexed Jobs
  runs/<job_name>/status/<index>_<night>.ecsv       # one status row per pod
  runs/<job_name>/download_status/                  # KOA download Job status rows
```

`$KECK_ETCS_DATA` (default `~/Projects/PypeIt/keck-etcs-data`) is the
local mirror, with the same layout. `keck_etcs.paths.night_dir()` and
`s3_prefix()` build the local path and the bucket key from the same parts.
`$KECK_ETCS_DATA/external/` (the XTcalc tarball) is local only.

`scripts/nautilus/s3_sync.py` (boto3) is the local access path. It is
idempotent by key and size:

```
python scripts/nautilus/s3_sync.py ls   mosfire/20220409/raw
python scripts/nautilus/s3_sync.py push mosfire/20220409/raw [--dry-run] [--jobs 8]
python scripts/nautilus/s3_sync.py pull mosfire/20220409 --include 'sens/*' 'harvest/*' [--force] [--dry-run]
python scripts/nautilus/s3_sync.py pull mosfire/20220409 --calibs      # also Calibrations/WaveCalib*
```

`AccessDenied`, invalid keys and a missing profile all exit with status 3
and name the credential source.

## 3. Image: build and push

`gitlab-registry.nrp-nautilus.io/profx/keck-etcs` is public, so pods need
no `imagePullSecret`. Build it on the Linux workstation (the laptop has no
Docker), from a clean keck-etcs work tree:

```
bash nautilus/build_image.sh            # build only
bash nautilus/build_image.sh --push     # build and push <version> and latest
```

- **Tag:** `keck_etcs.__version__`. Bump it in `keck_etcs/__init__.py`
  before every build that should be distinguishable.
- **`--push` refuses a dirty work tree,** so every pushed tag maps to a
  keck-etcs commit.
- **Contents:**
  - PypeIt at the pin (section 4);
  - keck_etcs with its data;
  - the PypeIt cache in `/opt/cache/pypeit` (MOSFIRE GitHub data, and the
    TellPCA grid checked against `telluric_grid.sha256`);
  - `KECK_ETCS_GIT_SHAS` (PypeIt and keck-etcs SHAs) as ENV and label.
- **Build guards:**
  - the PypeIt version ends with the pin's short SHA;
  - the TellPCA grid is in the cache;
  - `run_pypeit --help` and `pypeit_sensfunc --help` run;
  - `import keck_etcs.calib.harvest` works;
  - no SHA in `KECK_ETCS_GIT_SHAS` is `unknown`.
- **Registry login.** `--push` logs in through its own Docker config,
  `PUSH_DOCKER_CONFIG` (default `~/.docker-keck-etcs`). A deploy token is
  per project, and one Docker config holds one login per host. One-time
  setup, by the user:

  ```
  mkdir -p ~/.docker-keck-etcs
  printf '%s' '<token>' | DOCKER_CONFIG=~/.docker-keck-etcs docker login \
      gitlab-registry.nrp-nautilus.io -u 'gitlab+deploy-token-1383' --password-stdin
  ```

  The token itself stays with the user.
- **Registry hangs:** if a push stalls for more than about 10 minutes, on
  "Waiting" or at the manifest step, interrupt it and push again (or
  `DOCKER_CONFIG=~/.docker-keck-etcs docker push <image>:<tag>`). Layers
  already uploaded are skipped.
- **Check the push** with `docker manifest inspect <image>:<tag>`; `:latest`
  must show the new digest.
- **After a push,** record the tag in the table below and point the three
  Job manifests at it:
  - `night_job.yaml`, `validate_job.yaml`, `koa_download_job.yaml`;
  - in each: the `image:` line, the digest comment and
    `KECK_ETCS_IMAGE`;
  - then run `python nautilus/validate_manifests.py`.

| tag | PypeIt pin (`etc-fixes`) | keck-etcs | digest | notes |
|---|---|---|---|---|
| 0.2.5 | `bc18a3ba46d1d331da0875424c63999e578a4937` | `10a469f` | `sha256:69591fcbdb595ca0b24438f9b4cf803d0ad48dedbe36141a8d211e3b3a4daed4` | `construct_basename` fix (`/` in KOA target names); long2pos bar split; S15b sweep. **Current** |
| 0.2.4 | `fb6fb62c46383b09c5c13f1edcad97d3367fa0cd` | `58d5652` | `sha256:258e52f474676199e52a9a3969861445c542fcc6790940792e9de5ccac31d13b` | harvest `excluded_nonlinear` flag; S15b batch 1 |
| 0.2.3 | `fb6fb62c46383b09c5c13f1edcad97d3367fa0cd` | `fdfb1d7` | `sha256:99cc0d6379326b165270eba073a8b12ac716d71965a406781fe8a9293da42adf` | 4" bar wavelength transfer (`transfer_wavecal`), specphot object filter; S15a pilot |
| 0.2.2 | `fb4790520e4ccd49d39d42ed8438a614f307030b` | `09e9eee` | `sha256:920bd25f80483fe1c47ae70605bbd299229e6ecb593ca29f31fe5ebdfd746138` | long2pos bars, OH-arc cap (`MAX_OH_ARCS`), align-box fix, frozen monitor lines |
| 0.2.1 | `8017f47997d6417d797be6d0a0358d7acb8918b5` | `31488fa` | `sha256:1a8e82918c8a517089cbdf87a6c2ea9cc06345c9c9d4e8a21ae081925ed3cce3` | first pilot run |
| 0.2.0 | `8017f47997d6417d797be6d0a0358d7acb8918b5` | `8ab7cb9` | `sha256:aa538854d3b807696821f1df89bafff31ee325176576d60663df1ed7f291d978` | KOA download Job (`scripts/koa/`); S14b batch 1 downloads |
| 0.1.6 | `8017f47997d6417d797be6d0a0358d7acb8918b5` | `b2883b6` | `sha256:0c5e88fd838e24f9e658be3a01ffee276d80546df772a9da19da9c0ce912a357` | 2022-04-09 products of S10/S11 (LDS749B, J0841 validation) |
| 0.1.5 | `8017f47997d6417d797be6d0a0358d7acb8918b5` | `8678043` | `sha256:f3da5d0430e0af8c3826e45a702636c3ae818cf47dac0521333db1090e99bb01` | in-pod harvest; S6 closed (2026-10-04) |
| 0.1.4 | `8017f47997d6417d797be6d0a0358d7acb8918b5` | `83ba931` | `sha256:1a1d45f06bffb31dbfb965cbfaa927d011d9cb04f273775e3a48808a9f24cced` | `tell_npca = 3`; first image to pass every S4b gate |
| 0.1.3 | `8017f47997d6417d797be6d0a0358d7acb8918b5` | `d9f6d5f` | `sha256:2635e79f811b77b486fd9cf6243fcd7697d520af169cca52597b60a751ee4e64` | PypeIt `refine_trace` (off for MOSFIRE) |
| 0.1.2 | `275a012dfcb708d4f0eaeebd56d2513083244b24` | `534725e` | `sha256:51f39684e765569099d7f6e0b55668179f1f43ee05d4070546ff0e59ce1ab19c` | band-level `zp_agree` and `spec1d_agree` gates |
| 0.1.1 | `275a012dfcb708d4f0eaeebd56d2513083244b24` | `f211d4d` | `sha256:44faabcd081e96617ebeed3d05ce3b6d67883dab274c8cc17efa16ed36de09df` | S4b helpers (`gates.py`, `status_row.py`) |
| 0.1.0 | `275a012dfcb708d4f0eaeebd56d2513083244b24` | `d4c5871` | `sha256:12793464bc5131985f1289984b7fdb138605861b78abb7e49ecd82400fec7866` | dry-run image (S4a) |

Images are about 2.2 GB.

## 4. The PypeIt pin

- **The pin files:**
  - `pypeit_pin.txt` holds the one PypeIt commit the image installs, as a
    full SHA.
  - `build_image.sh` requires it to be on the history of a branch in
    `PIN_BRANCHES`, default `"develop etc-fixes"`, and warns when that
    branch is not `develop`.
  - `pypeit_pin_allowlist.txt` lists the paths that may differ locally
    without affecting a MOSFIRE J reduction.
- **Today:** the pin is `bc18a3b` on PypeIt's `etc-fixes` branch.
  - That branch is `develop` (`f3a1f1d`) plus the MOSFIRE fixes found while
    reducing:
    - `pypeit_cache_github_data`;
    - `refine_trace`;
    - `get_arc_extract_center`;
    - `alignment_box_rows`;
    - `transfer_wavecal`;
    - `long2pos_bar_widths`;
    - `construct_basename`.
  - This is a recorded exception to D31 until `etc-fixes` merges into
    `develop`.
- **`scripts/check_pypeit_pin.py`** checks the local checkout against the
  pin and the allow-list (D35). It writes
  `$KECK_ETCS_DATA/pypeit_pin_check.json`; `--image TAG` also checks the
  image's `KECK_ETCS_GIT_SHAS`. Inside the image it runs in image mode: it
  passes when `KECK_ETCS_GIT_SHAS.pypeit` equals the pin.
- **Moving the pin:**
  1. Edit `pypeit_pin.txt` (one full SHA).
  2. Bump `keck_etcs.__version__`.
  3. Commit, build, push.
  4. Add a row to the table above, and record the new image and pin in the
     next `CHANGES.md` release.
  5. `check_pypeit_pin.py --image <tag>` must pass.

  Any night reduced afterwards carries the new `pypeit_git_sha`. Until the
  local checkout is at the new pin, the local check fails by design.
- **Pending:** the MOSFIRE read-noise fix (`ronoise` from
  `SAMPMODE`/`NUMREADS`, design D19; patch in
  `nautilus/patches/pypeit_mosfire_ronoise.patch`) is committed on
  `etc-fixes` as `38bb1b7` but not pinned yet. Move the pin to it, with
  image 0.2.6, before the next batch.

## 5. kubectl idioms and the credentials test

Every manifest's header has its delete, apply and follow lines:

```
kubectl -n pypeit delete pod keck-etcs-inspect --ignore-not-found
kubectl apply -f nautilus/inspect_pod.yaml
kubectl -n pypeit logs -f keck-etcs-inspect
```

Other useful commands:

```
kubectl -n pypeit get pods -l app=keck-etcs                 # role=night, validate, koa-download, inspect
kubectl -n pypeit describe pod <pod>                         # scheduling, mount and OOM errors
kubectl -n pypeit get job <job> -o jsonpath='{.status}'      # failedIndexes, completedIndexes
kubectl -n pypeit get secrets                                # names only; never -o yaml
kubectl apply --dry-run=server -f <manifest>                 # validate without creating
```

- **Another secret:** apply through `sed`:
  `sed "s/prp-s3-credentials/$KECK_ETCS_S3_SECRET/" <manifest> | kubectl apply -f -`.
- **Helper files** reach pods as ConfigMaps:
  `kubectl -n pypeit create configmap <name> --from-file=<files> --dry-run=client -o yaml | kubectl apply -f -`.
  Anything over the 1 MiB limit goes to S3.

**Credentials test (`inspect_pod.yaml`).** A throwaway `python:3.12-slim`
pod that mounts the secret, installs boto3 and lists `s3://keck-etcs/`
through the in-cluster endpoint.

- It prints the object count and the keys under `mosfire/20220409/raw/`
  (17: 16 frames plus `manifest.ecsv`).
- It prints `ACCESS_RESULT OK` or `ACCESS_RESULT <code>`, and ends with
  `INSPECT_DONE`.
- **If the default secret fails the test,** create a dedicated one from a
  credentials file that holds only a `[default]` section with the Nautilus
  keys:

  ```
  kubectl -n pypeit create secret generic keck-etcs-s3-credentials \
      --from-file=credentials=<file with only [default]>
  export KECK_ETCS_S3_SECRET=keck-etcs-s3-credentials
  ```

  Then re-run the test through the `sed` line above.

## 6. Reducing a batch of nights

**1. Write the night manifest.** Create
`nautilus/manifests/nights_<batch>.csv`, with columns `night, instrument,
s3_prefix, standard, slit, spec2d, notes`, from the KOA search
(`scripts/koa/`). Push it to `s3://keck-etcs/manifests/`.

**2. Download the raw frames** (`koa_download_job.yaml`, D37):

```
kubectl -n pypeit create configmap keck-etcs-koa-nights \
  --from-file=nights.csv=nautilus/manifests/nights_<batch>.csv --dry-run=client -o yaml | kubectl apply -f -
# set spec.completions to the number of rows, then
kubectl -n pypeit delete job keck-etcs-koa-download --ignore-not-found
kubectl apply -f nautilus/koa_download_job.yaml
kubectl -n pypeit logs -f job/keck-etcs-koa-download          # DOWNLOAD_DONE per pod
python scripts/koa/download_mosfire_night.py --collect keck-etcs-koa-download --to-s3
```

- Parallelism is 2, for politeness to KOA.
- "No standard" and "no calibs" end a pod successfully after its status
  row; download failures are retried.
- The local fallback is the same script with `--to-s3` on the
  workstation.

**3. Reduce** (`night_job.yaml`, D33):

```
kubectl -n pypeit create configmap keck-etcs-nights \
  --from-file=nights.csv=nautilus/manifests/nights_<batch>.csv --dry-run=client -o yaml | kubectl apply -f -
# set spec.completions to the number of rows, then
kubectl -n pypeit delete job keck-etcs-nights --ignore-not-found
kubectl apply -f nautilus/night_job.yaml
kubectl -n pypeit get pods -l app=keck-etcs,role=night
kubectl -n pypeit logs <pod>                                   # NIGHT_DONE per pod
```

What a night pod does (`night_job.yaml` and `validate_job.yaml` share one
script block; `python nautilus/validate_manifests.py` checks the YAML,
`bash -n`, and that the two blocks are identical):

1. Prints a PROVENANCE block: image tag and digest, `KECK_ETCS_GIT_SHAS`,
   the versions, the pin, the job, index, pod and node.
2. Reads its row (`JOB_COMPLETION_INDEX`) of the manifest mounted at
   `/opt/manifest/nights.csv`.
3. Skips the night if `s3://keck-etcs/<s3_prefix>/run_manifest.json`
   exists, unless `REPLACE=1`. Products are always pushed with `--force`,
   so a re-reduction replaces same-size stale files.
4. Runs, in order:
   - `reduce_standard.py <night> --scratch /scratch --s3-pull`: the pin
     check in image mode, `pypeit_setup`, patching the pypeit file (standard
     typing, nod pairs, `long2pos_specphot` bar split, OH-arc cap),
     `run_pypeit` and QA;
   - `build_sensfunc.py`: per-frame and coadd sensfuncs with the packaged
     `.sens`;
   - `gates.py`;
   - the harvest: the per-standard row, the curve and
     `<night>_monitor.ecsv`.
5. Pushes the products, with `run_manifest.json` last, so a half-pushed
   night is not skipped later.
6. Writes and pushes its status row
   (`runs/<job>/status/<index>_<night>.ecsv`) and prints `NIGHT_DONE`.

**Exit codes and retries.**

- **0, success:** the gates pass and the push completed.
- **2, data outcome:** `no calibs`, `setup failed`, `no trace`,
  `sens failed`, `gate failed` or `pin check failed`. The
  `podFailurePolicy` turns it into `FailIndex`: recorded, not retried,
  and the other indexes keep running.
- **1, infrastructure:** `pull failed`, `push failed`, `reduce failed` or
  an OOM kill. Retried once per index (`backoffLimitPerIndex: 1`).
- **Evictions and preemptions** (`DisruptionTarget`) are ignored and rerun.

Re-applying a whole Job resumes it, because finished nights skip
themselves.

**Resources.** Each pod requests cpu 4, memory 16Gi and 30Gi ephemeral
storage (60Gi limit), with `OMP_NUM_THREADS=4`, a 6 h deadline and
parallelism 4. Measured so far:

- PypeIt is about one core;
- peak memory 5.8-13.6 GiB (a SPEC2D night with 36 science frames reaches
  11.2 GiB with the OH-arc cap; it was OOM-killed at 16 GiB without it);
- scratch up to 8 GB;
- wall-clock 5-80 min per night, varying by about 2x between nodes.

The header of `night_job.yaml` keeps the table. Each pod's `USAGE` line
and `run_manifest.json` `pod_usage` record the actual values.

**Dry run** (`validate_job.yaml`: 2022-04-09 against the local reference,
`backoffLimit: 0`; needed after any change to the reduction):

```
python scripts/nautilus/stage_reference.py 20220409 --push
kubectl -n pypeit create configmap keck-etcs-nights-dryrun \
  --from-file=nights.csv=nautilus/manifests/nights_dryrun.csv --dry-run=client -o yaml | kubectl apply -f -
kubectl -n pypeit delete job keck-etcs-validate --ignore-not-found
kubectl apply -f nautilus/validate_job.yaml
kubectl -n pypeit logs -f job/keck-etcs-validate                 # GATES: PASS ... NIGHT_DONE
```

## 7. Sweeping failures

```
python nautilus/night_failures.py keck-etcs-nights        # per-night status + nautilus/manifests/sweep_<job>.csv
python nautilus/status_table.py                            # per-night table from run_manifest.json (store-only)
```

- `night_failures.py` reads every status row of the Job and keeps each
  night's **latest** row, by `time`. Older rows under the same Job name,
  such as a pilot's, do not count.
- It writes a sweep manifest of the nights whose latest status is not
  `success`.
- **Diagnose from the S3 artefacts:** `run.log`, `pod.log` and the
  `run_manifest.json` that a failed pod still pushes.
- **Fix the cause:** code, a PypeIt fix on the pinned branch plus a new
  image, or a manifest note.
- **Run the sweep:** `night_job.yaml` under a new Job name (e.g.
  `keck-etcs-nights-sweep1`) with `sweep_<job>.csv` as its ConfigMap.
- A night that fails twice for a data reason (`no calibs`, `no trace`) is
  recorded as such, not retried again.

## 8. Syncing products back

```
python scripts/nautilus/s3_sync.py pull mosfire/<night> --force \
    --include 'sens/*' 'harvest/*' 'redux/Science/spec1d_*' 'redux/*.pypeit' \
    run_manifest.json run.log gates.json pypeit_pin_check.json
python scripts/nautilus/s3_sync.py pull mosfire/<night> --calibs   # WaveCalib* for the LSF/monitor work
python nautilus/verify_nights.py <night> [<night> ...]             # every product sha256 = run_manifest.json
```

- **Why `--force`:** `s3_sync` is idempotent by key and *size*, and two
  reductions of one night give different files of the same size. Use
  `--force` whenever the mirror may hold another reduction.
- Keep the `--include`, so `raw/` and `reference/` are left alone.
- `verify_nights.py` must print ALL OK before the products are harvested or
  merged.

## 9. Backup

Nautilus S3 is not backed up. `scripts/nautilus/backup_products.py` copies
the high-level products (D39, design 4.8.9) with `rclone` from
`nautilus_s3:keck-etcs/` to the Google shared drive `AIOcean:keck-etcs/`.

- **Included, per night:** `sens/**`, `harvest/**`, `run_manifest.json`,
  `run.log`, `redux/*.pypeit`, `redux/Science/spec1d_*` and
  `raw/manifest.ecsv`.
- **Included, at the bucket root:** `manifests/**` and `runs/**`.
- **Excluded:** raw frames, `spec2d_*`, `Calibrations/` and `QA/`.

```
python scripts/nautilus/backup_products.py                          # dry run of the whole set
python scripts/nautilus/backup_products.py --run                    # after every successful batch
python scripts/nautilus/backup_products.py --run --release <calib_version>   # at a release (section 10)
python scripts/nautilus/backup_products.py --check-only
```

- **What `--run` does:** it copies, then runs `rclone check --one-way`, and
  writes a JSON summary to `$KECK_ETCS_DATA/runs/backup/`.
- **Success:** 0 missing, 0 differ, 0 errors (COMPLETE).
- **`--release`:** freezes the contributing nights under
  `AIOcean:keck-etcs/releases/<calib_version>/`.
- The rclone remotes hold the credentials; nothing secret is printed.
- **Last backups:** after S15b batch 1, and the release
  `mosfire-J-2026.10` (801 files, COMPLETE, 2026-10-08).

## 10. Cutting a calibration release

A calibration release is one commit touching only `keck_etcs/data/` and
`CHANGES.md`, tagged `mosfire-J-YYYY.MM` (design 5.5, D28).

1. Reduce, sweep, sync back and verify the new nights (sections 6-8), then
   back up the batch (section 9).
2. Merge the harvests:
   `python scripts/mosfire/harvest_sens.py --merge $KECK_ETCS_DATA/mosfire/<night>/harvest ...`.
3. Set `CALIB_VERSION` in `scripts/mosfire/combine_throughput.py` and run
   it. It rebuilds the era curves and updates their `index.yaml` entries.
4. Run the trend and monitor plots (`plot_throughput_trend.py`,
   `plot_monitor_trends.py`), then `verify_release.py`, which must print
   ALL CHECKS PASS.
5. If `compute()` outputs change, run
   `scripts/regen_regression_fixtures.py --regen --note "..."`.
6. Write the `CHANGES.md` section:
   - the standards added and excluded;
   - the era medians before and after;
   - the detector-table changes;
   - every image tag with its digest and PypeIt pin, as `verify_release.py`
     prints them.
7. Run `python scripts/check_docs.py`. It checks that `index.yaml`,
   `CHANGES.md`, this table and `meta.calib_version` agree.
8. The user commits (code first, then the release) and tags.
9. Run `backup_products.py --run --release <calib_version>`.
