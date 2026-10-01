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
| 0.1.0 | `275a012dfcb708d4f0eaeebd56d2513083244b24` (`etc-fixes`) | `d4c5871` | `sha256:12793464bc5131985f1289984b7fdb138605861b78abb7e49ecd82400fec7866` | 2.16 GB | dry-run image (S4a). Pin = develop `f3a1f1d` + the `pypeit_cache_github_data` fix; a recorded exception to D31 until it merges into develop |

**Re-pinning.** Edit `nautilus/pypeit_pin.txt` (one full SHA), bump
`keck_etcs.__version__`, rebuild, push, and add a row here and to
`CHANGES.md`. `scripts/check_pypeit_pin.py --image <tag>` must pass. It
requires the image's `KECK_ETCS_GIT_SHAS.pypeit` to equal the pin exactly;
the local checkout's SHA is only reported.
