# keck-etcs on Nautilus (v0)

How this repository uses the NRP Nautilus cluster: storage in S3 now,
reductions in Kubernetes Jobs later (design 4.8, plan steps S0 and S1b).

## Namespace, bucket, credentials

- **Namespace:** `pypeit`. The `kubectl` context is `nautilus`.
- **Bucket:** `s3://keck-etcs` on Nautilus S3 (Ceph RGW), path-style
  addressing.
  - Endpoint from outside the cluster: `https://s3-west.nrp-nautilus.io`.
  - Endpoint inside the cluster: `http://rook-ceph-rgw-nautiluss3.rook`.
  - Scripts read the endpoint from `ENDPOINT_URL`.
- **The bucket is private** (design D32). Only the owner's keys can list,
  read or write it, and anonymous requests get HTTP 403. Nothing in it is
  shared by URL. WMKO and collaborators get the products through the ECSV and
  FITS files committed to git.
- **Local credentials:** an AWS profile holding the Nautilus keys. Select it
  with `AWS_PROFILE` (default `default`), or set `AWS_ACCESS_KEY_ID` and
  `AWS_SECRET_ACCESS_KEY`. There is no anonymous fallback.
- **In-pod credentials:** a Secret in `pypeit`, mounted, never copied, at
  `/root/.aws/credentials` (`subPath: credentials`), with `HOME=/root`.
  Manifests take its name from `KECK_ETCS_S3_SECRET`:
  - `prp-s3-credentials`: the default. It is the namespace's existing S3
    secret.
  - `keck-etcs-s3-credentials`: the fallback, if the default cannot read
    `s3://keck-etcs` (see below).
- **No secret value ever appears in this repository,** in a log or in a
  pod's output.

## Layout (design 4.2)

```
s3://keck-etcs/
  mosfire/<YYYYMMDD>/raw/*.fits, manifest.ecsv     # KOA frames + per-frame manifest (sha256)
  mosfire/<YYYYMMDD>/redux/<night>.pypeit           # the pypeit file actually run
  mosfire/<YYYYMMDD>/redux/Calibrations/            # WaveCalib*, Flat*, Edges*, Tilts*
  mosfire/<YYYYMMDD>/redux/Science/spec1d_*.fits    # spec1d always; spec2d only when SPEC2D=1
  mosfire/<YYYYMMDD>/redux/QA/                      # PypeIt QA PNGs
  mosfire/<YYYYMMDD>/sens/sens_*.fits, *_QA.png     # pypeit_sensfunc output and telluric QA
  mosfire/<YYYYMMDD>/harvest/<standard>_<date>.ecsv # per-standard row + curve
  mosfire/<YYYYMMDD>/run_manifest.json, run.log     # provenance and the tee'd pod log
  manifests/nights_<batch>.csv                      # night manifests that drive the Indexed Jobs
  runs/<job_name>/status.ecsv                       # per-night status written by the job
```

`$KECK_ETCS_DATA` (default `~/Projects/PypeIt/keck-etcs-data`) is the local
mirror, with the same layout. `keck_etcs.paths.night_dir()` and
`s3_prefix()` build the local path and the bucket key from the same parts.
`$KECK_ETCS_DATA/external/` (the XTcalc tarball) is local only.

## Sync helper

`scripts/nautilus/s3_sync.py` uses boto3 and is idempotent by key and size:

```
python scripts/nautilus/s3_sync.py ls   mosfire/20220409/raw
python scripts/nautilus/s3_sync.py push mosfire/20220409/raw [--dry-run] [--jobs 8]
python scripts/nautilus/s3_sync.py pull mosfire/20220409 --include 'sens/*' 'harvest/*' [--dry-run]
```

`AccessDenied`, invalid keys and a missing profile all exit with status 3
and name the credential source.

## PypeIt pin

- `pypeit_pin.txt` holds the one PypeIt commit on `develop` that the image
  installs.
- `pypeit_pin_allowlist.txt` lists the paths that may differ locally
  without affecting a MOSFIRE J reduction.
- `scripts/check_pypeit_pin.py` checks the local checkout against both
  (design D35). It writes `$KECK_ETCS_DATA/pypeit_pin_check.json` for the
  reduction's `run_manifest.json`. `--image TAG` also checks the image's
  `KECK_ETCS_GIT_SHAS`.
- `telluric_grid.sha256` is the sha256 of `TellPCA_3000_26000_R10000.fits`,
  which the image build checks.

## kubectl idioms

Every manifest's header has these three lines (delete, apply, follow):

```
kubectl -n pypeit delete pod keck-etcs-inspect --ignore-not-found
kubectl apply -f nautilus/inspect_pod.yaml
kubectl -n pypeit logs -f keck-etcs-inspect
```

Other useful commands:

```
kubectl -n pypeit get pods -l app=keck-etcs
kubectl -n pypeit describe pod keck-etcs-inspect       # scheduling / mount errors
kubectl -n pypeit get secrets                           # names only; never `-o yaml`
kubectl apply --dry-run=server -f <manifest>            # validate without creating
```

- **Choosing the secret:** to use a secret other than the default, apply the
  manifest through `sed`:
  `sed "s/prp-s3-credentials/$KECK_ETCS_S3_SECRET/" nautilus/inspect_pod.yaml | kubectl apply -f -`.
- **Helper scripts:** these go to pods as ConfigMaps:
  `kubectl -n pypeit create configmap <name> --from-file=<files> --dry-run=client -o yaml | kubectl apply -f -`.
  Anything over the 1 MiB ConfigMap limit goes to S3 instead.

## Credentials test: `inspect_pod.yaml`

- **What it does:** a throwaway `python:3.12-slim` pod that mounts the
  secret, installs boto3, lists `s3://keck-etcs/` through the in-cluster
  endpoint, and prints the object count and the keys under
  `mosfire/20220409/raw/`. The count should be 17: 16 frames plus
  `manifest.ecsv`.
- **Reading the log:** it prints `ACCESS_RESULT OK` or `ACCESS_RESULT <code>`
  (e.g. `AccessDenied`, `InvalidAccessKeyId`), and ends with `INSPECT_DONE`
  on success.
- **If `prp-s3-credentials` fails the test,** create a dedicated secret from
  the local credentials file, which holds the keck-etcs keys under
  `[default]`:

  ```
  kubectl -n pypeit create secret generic keck-etcs-s3-credentials \
      --from-file=credentials=$HOME/.aws/credentials
  export KECK_ETCS_S3_SECRET=keck-etcs-s3-credentials
  kubectl -n pypeit delete pod keck-etcs-inspect --ignore-not-found
  sed "s/prp-s3-credentials/$KECK_ETCS_S3_SECRET/" nautilus/inspect_pod.yaml | kubectl apply -f -
  kubectl -n pypeit logs -f keck-etcs-inspect
  ```

  This copies every profile in `~/.aws/credentials` into the Secret. To
  limit it to the Nautilus keys, first write a file that holds only a
  `[default]` section and pass that file instead.

## Image

`gitlab-registry.nrp-nautilus.io/profx/keck-etcs` is public, so pods need
no `imagePullSecret`. It is built on the Linux workstation by
`bash nautilus/build_image.sh [--push]` from `nautilus/Dockerfile` (design
4.8.2). `--push` refuses a dirty work tree, so every pushed tag maps to a
keck-etcs commit.
- **Contents:** PypeIt at the pin, keck_etcs with its data files, and the
  PypeIt cache in `/opt/cache/pypeit` (MOSFIRE GitHub data and the TellPCA
  grid, its sha256 checked).
- **Provenance:** baked in as `KECK_ETCS_GIT_SHAS`.
- **Registry hangs:** if a push stalls for more than about 10 minutes, on
  "Waiting" or at the manifest step, interrupt it and push again. Layers
  already uploaded are skipped.

| tag | PypeIt pin | keck-etcs | digest | size | notes |
|---|---|---|---|---|---|
| 0.1.5 | `8017f47997d6417d797be6d0a0358d7acb8918b5` (`etc-fixes`) | `8678043` | `sha256:f3da5d0430e0af8c3826e45a702636c3ae818cf47dac0521333db1090e99bb01` | 2.16 GB | adds the in-pod harvest (`keck_etcs.calib.harvest`, guard in the build); S6 closed (2026-10-04) |
| 0.1.4 | `8017f47997d6417d797be6d0a0358d7acb8918b5` (`etc-fixes`) | `83ba931` | `sha256:1a1d45f06bffb31dbfb965cbfaa927d011d9cb04f273775e3a48808a9f24cced` | 2.16 GB | `tell_npca = 3` in the packaged `.sens`; first image to pass every S4b gate (dry run 2026-10-02) |
| 0.1.3 | `8017f47997d6417d797be6d0a0358d7acb8918b5` (`etc-fixes`) | `d9f6d5f` | `sha256:2635e79f811b77b486fd9cf6243fcd7697d520af169cca52597b60a751ee4e64` | 2.16 GB | adds PypeIt `refine_trace` (off for MOSFIRE); fixes the 0037 extraction walk |
| 0.1.2 | `275a012dfcb708d4f0eaeebd56d2513083244b24` (`etc-fixes`) | `534725e` | `sha256:51f39684e765569099d7f6e0b55668179f1f43ee05d4070546ff0e59ce1ab19c` | 2.16 GB | band-level `zp_agree` and `spec1d_agree` gates |
| 0.1.1 | `275a012dfcb708d4f0eaeebd56d2513083244b24` (`etc-fixes`) | `f211d4d` | `sha256:44faabcd081e96617ebeed3d05ce3b6d67883dab274c8cc17efa16ed36de09df` | 2.16 GB | S4b helpers (`gates.py`, `status_row.py`), `s3_sync --include/--force` |
| 0.1.0 | `275a012dfcb708d4f0eaeebd56d2513083244b24` (`etc-fixes`) | `d4c5871` | `sha256:12793464bc5131985f1289984b7fdb138605861b78abb7e49ecd82400fec7866` | 2.16 GB | dry-run image (S4a). Pin = develop `f3a1f1d` + the `pypeit_cache_github_data` fix; a recorded exception to D31 until it merges into develop |

**Registry login.** `--push` logs in through its own Docker config
directory, `PUSH_DOCKER_CONFIG` (default `~/.docker-keck-etcs`). A deploy
token is per project, and one Docker config holds one login per registry
host, so a login for PAB in `~/.docker` used to overwrite the keck-etcs one
(push `denied`, 2026-10-02). One-time setup, by the user:
`mkdir -p ~/.docker-keck-etcs && printf '%s' '<token>' | DOCKER_CONFIG=~/.docker-keck-etcs docker login gitlab-registry.nrp-nautilus.io -u 'gitlab+deploy-token-1383' --password-stdin`.
PAB can do the same with `~/.docker-pab`.

**Re-pinning.** Edit `nautilus/pypeit_pin.txt` (one full SHA), bump
`keck_etcs.__version__`, rebuild, push, and add a row here and to
`CHANGES.md`. `scripts/check_pypeit_pin.py --image <tag>` must pass. It
requires the image's `KECK_ETCS_GIT_SHAS.pypeit` to equal the pin exactly;
the local checkout's SHA is only reported.

## Operating the reductions (S4b)

**What a night pod does** (`night_job.yaml` and `validate_job.yaml`, which
share one script block; `python nautilus/validate_manifests.py` checks the
YAML, `bash -n` and that the two blocks are identical):
1. Prints a PROVENANCE block: image tag and digest, `KECK_ETCS_GIT_SHAS`,
   the PypeIt and keck_etcs versions, the pin, and the job, index, pod and
   node.
2. Reads its row (`JOB_COMPLETION_INDEX`) of the night manifest mounted from
   the ConfigMap at `/opt/manifest/nights.csv`. The columns are `night,
   instrument, s3_prefix, standard, slit, spec2d, notes`.
3. **Skips** the night if `s3://keck-etcs/<s3_prefix>/run_manifest.json`
   exists, unless `REPLACE=1`. `REPLACE=1` re-reduces and pushes with
   `--force`.
4. Runs `reduce_standard.py <night> --scratch /scratch --s3-pull` (pin
   check in image mode, setup, patch, `run_pypeit`, QA), then
   `build_sensfunc.py` (per-frame and coadd sensfunc with the packaged
   `.sens`), then `gates.py` (with `--reference` when `GATES_REFERENCE` is
   set), then the harvest (once S6 exists).
5. Pushes `redux/`, `sens/`, `harvest/`, `run.log`, `pod.log`,
   `pypeit_pin_check.json` and `gates.json`, then `run_manifest.json`
   **last**, so a half-pushed night is not skipped later. `spec2d` is pushed
   only when `SPEC2D=1`.
6. Writes and pushes a status row,
   `runs/<job>/status/<index>_<night>.ecsv` (one object per pod), and
   prints `NIGHT_DONE`.

On any failure the pod pushes `run_manifest.json`, `run.log` and `pod.log`
for diagnosis, writes the status row and exits 1. The statuses are `no
calibs`, `setup failed`, `reduce failed`, `no trace`, `sens failed`,
`gate failed`, `push failed`, `pull failed` and `pin check failed`
(`nautilus/status_row.py`).

**Dry run** (2022-04-09 against the local reference):

```
python scripts/nautilus/stage_reference.py 20220409 --push       # s3://keck-etcs/mosfire/20220409/reference/
kubectl -n pypeit create configmap keck-etcs-nights-dryrun \
  --from-file=nights.csv=nautilus/manifests/nights_dryrun.csv --dry-run=client -o yaml | kubectl apply -f -
kubectl -n pypeit delete job keck-etcs-validate --ignore-not-found
kubectl apply -f nautilus/validate_job.yaml
kubectl -n pypeit logs -f job/keck-etcs-validate                 # GATES: PASS ... NIGHT_DONE
python scripts/nautilus/s3_sync.py pull mosfire/20220409 --force --include 'redux/*' 'sens/*' 'harvest/*' \
    run_manifest.json run.log pod.log pypeit_pin_check.json gates.json   # pod products into the mirror
```

**A batch:**

```
kubectl -n pypeit create configmap keck-etcs-nights \
  --from-file=nights.csv=nautilus/manifests/nights_<batch>.csv --dry-run=client -o yaml | kubectl apply -f -
# edit spec.completions in night_job.yaml to the number of rows, then
kubectl -n pypeit delete job keck-etcs-nights --ignore-not-found
kubectl apply -f nautilus/night_job.yaml
kubectl -n pypeit get pods -l app=keck-etcs,role=night
kubectl -n pypeit logs <pod>                                     # per night
python nautilus/night_failures.py keck-etcs-nights               # status.ecsv + sweep manifest of failed nights
python nautilus/status_table.py                                  # per-night table from run_manifest.json (store-only)
```

**Pulling over local products.** `s3_sync` is idempotent by key and *size*,
and a re-reduction of the same night gives different files of the same size
(every spec1d of 2022-04-09 is 423360 bytes). Use `pull --force` (with
`--include`, to leave `raw/` and `reference/` alone) when the mirror already
holds another reduction of the night. Then check that every
`run_manifest.json` `product_sha256` matches the local file.

**Retries.**
- A sweep job is `night_job.yaml` applied with
  `nautilus/manifests/sweep_<job>.csv` as its ConfigMap.
- Nights that are already done skip themselves, so re-applying a whole job
  after a preemption resumes it.
- A night that fails twice for a data reason (`no calibs`, `no trace`) is
  not retried. `night_failures.py` lists it instead.

**Resources.** The initial guess (design 4.8.4) is cpu 4, memory 16Gi,
ephemeral 30Gi request / 60Gi limit, `OMP_NUM_THREADS=4`, and a 6 h
deadline. The dry run's measured wall-clock, peak memory (cgroup
`memory.peak`) and scratch use are in each pod's log (`USAGE`), in
`run_manifest.json` (`pod_usage`) and in the header of `night_job.yaml`.
