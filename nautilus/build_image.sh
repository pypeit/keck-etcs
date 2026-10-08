#!/usr/bin/env bash
# Build (and optionally push) the keck-etcs image for Nautilus (design D31, 4.8.2).
#
#   bash nautilus/build_image.sh            # stage, check the pin, build, smoke-test
#   bash nautilus/build_image.sh --push     # ... then push :<version> and :latest,
#                                           #     and inspect the manifest
#
# Runs on the Linux workstation. --push needs a clean, committed work tree,
# so the tag always maps to a commit, and the keck-etcs deploy token logged
# in to its OWN Docker config directory, PUSH_DOCKER_CONFIG (default
# ~/.docker-keck-etcs), so that logins for other projects on the same
# registry host (e.g. PAB) never overwrite it. One-time setup:
#   mkdir -p ~/.docker-keck-etcs && printf '%s' '<token>' | \
#     DOCKER_CONFIG=~/.docker-keck-etcs docker login gitlab-registry.nrp-nautilus.io \
#     -u 'gitlab+deploy-token-1383' --password-stdin
# Only the push and manifest steps use that config; the build uses the default.
# The image is PUBLIC: the script refuses to build if a credentials file is
# in the build context.
#
# Environment overrides: IMAGE, TAG (default: keck_etcs.__version__),
# STAGE (default /tmp/keck_etcs_build_ctx), PYPEIT_REPO, PUSH_DOCKER_CONFIG.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
IMAGE=${IMAGE:-gitlab-registry.nrp-nautilus.io/profx/keck-etcs}
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO/keck_etcs/__init__.py")
TAG=${TAG:-$VERSION}
STAGE=${STAGE:-/tmp/keck_etcs_build_ctx}
PYPEIT_REPO=${PYPEIT_REPO:-https://github.com/pypeit/PypeIt.git}
# PypeIt branches whose history may contain the pin. Design D31 says develop
# only; etc-fixes is a recorded exception (since 2026-09-30) until its fixes
# merge into develop: pin 275a012 = develop f3a1f1d + the
# pypeit_cache_github_data fix; pin 8017f47 (2026-10-02) adds the refine_trace
# extraction parameter, off for MOSFIRE; pin fb47905 (2026-10-07, S15a) moves
# MOSFIRE arc extraction off the alignment box of LONGSLIT (align) masks
# (Spectrograph.get_arc_extract_center); pin fb6fb62 (2026-10-07) calibrates
# the 4-arcsec long2pos_specphot bars from their 0.7-arcsec neighbors
# (Spectrograph.transfer_wavecal); pin bc18a3b (2026-10-08) replaces path
# separators in target names of output files (outputfiles.construct_basename).
# Then the pin moves to the merge
# commit and this goes back to develop.
PIN_BRANCHES=${PIN_BRANCHES:-"develop etc-fixes"}
PUSH_DOCKER_CONFIG=${PUSH_DOCKER_CONFIG:-$HOME/.docker-keck-etcs}
PUSH=0
[[ "${1:-}" == "--push" ]] && PUSH=1
if [[ $PUSH -eq 1 ]]; then
  # fail now, not after a 5-minute build, if this project's login is missing
  python3 -c "import json, sys; a = json.load(open(sys.argv[1])).get('auths', {}); sys.exit(0 if sys.argv[2] in a else 1)" \
      "$PUSH_DOCKER_CONFIG/config.json" "${IMAGE%%/*}" 2>/dev/null \
    || { echo "FATAL: no login for ${IMAGE%%/*} in $PUSH_DOCKER_CONFIG (see the one-time setup in this script's header)"; exit 1; }
fi

PIN=$(head -1 "$REPO/nautilus/pypeit_pin.txt" | tr -d '[:space:]')
[[ ${#PIN} -eq 40 ]] || { echo "FATAL: nautilus/pypeit_pin.txt must hold one full SHA"; exit 1; }
KSHA=$(git -C "$REPO" rev-parse --short HEAD)
if [[ -n "$(git -C "$REPO" status --porcelain)" ]]; then
  if [[ $PUSH -eq 1 ]]; then
    echo "FATAL: --push needs a clean work tree (commit first); git status:"
    git -C "$REPO" status --short
    exit 1
  fi
  KSHA="${KSHA}-dirty"
  echo "WARNING: work tree is dirty; keck_etcs SHA recorded as $KSHA (local build only)"
fi
echo "== image $IMAGE:$TAG  (keck_etcs $VERSION @ $KSHA, PypeIt pin $PIN)"

# --- 1. the pin must be on the history of one of PIN_BRANCHES. Checked in a
# throwaway treeless clone, never in the user's PypeIt checkout. The same clone
# gives the pin's pyproject.toml, from which the dependency layer is built.
SCRATCH=$(mktemp -d)
trap 'rm -rf "$SCRATCH"' EXIT
echo "== checking the pin against $PYPEIT_REPO ($PIN_BRANCHES; treeless clone in $SCRATCH)"
git clone -q --filter=tree:0 --no-checkout "$PYPEIT_REPO" "$SCRATCH/PypeIt"
ON=""
for b in $PIN_BRANCHES; do
  if git -C "$SCRATCH/PypeIt" rev-parse -q --verify "origin/$b" > /dev/null \
     && git -C "$SCRATCH/PypeIt" merge-base --is-ancestor "$PIN" "origin/$b"; then
    ON="$b"; break
  fi
done
[[ -n "$ON" ]] || { echo "FATAL: pin $PIN is not on any of: $PIN_BRANCHES"; exit 1; }
echo "   pin is an ancestor of origin/$ON ($(git -C "$SCRATCH/PypeIt" rev-parse --short "origin/$ON"))"
[[ "$ON" == develop ]] || echo "WARNING: pin is on $ON, not develop (recorded exception to D31)"

# --- 2. staging context: this repo without .git and caches, plus the pin's deps
echo "== staging build context in $STAGE"
rm -rf "$STAGE"
mkdir -p "$STAGE"
rsync -a --delete \
  --exclude '.git' --exclude '.claude' --exclude '__pycache__' --exclude '*.egg-info' \
  --exclude '.pytest_cache' --exclude 'docs/figures' --exclude 'build' --exclude 'dist' \
  "$REPO/" "$STAGE/keck-etcs/"
git -C "$SCRATCH/PypeIt" show "$PIN:pyproject.toml" > "$SCRATCH/pyproject.toml"
python3 - "$SCRATCH/pyproject.toml" > "$STAGE/pypeit_requirements.txt" <<'PY'
import sys, tomllib
deps = tomllib.load(open(sys.argv[1], 'rb'))['project']['dependencies']
print(f'# PypeIt dependencies at the pin (pyproject.toml), written by build_image.sh')
print('\n'.join(deps))
PY
echo "   $(grep -vc '^#' "$STAGE/pypeit_requirements.txt") PypeIt dependencies; context $(du -sh "$STAGE" | cut -f1)"

# nothing secret may enter a public image
BAD=$(find "$STAGE" \( -name credentials -o -name '.netrc' -o -name '*.pem' -o -name '.aws' \
      -o -name 'config.json' -o -name '*.key' \) -print; \
      grep -rIl -e 'aws_secret''_access_key' -e 'BEGIN .*PRIVATE'' KEY' "$STAGE" || true)
# (the patterns are split so that this script does not match itself)
[[ -z "$BAD" ]] || { echo "FATAL: credential-like files in the build context:"; echo "$BAD"; exit 1; }
echo "   no credential files in the context"

# --- 3. build
SHAS=$(printf '{"pypeit":"%s","keck_etcs":"%s"}' "$PIN" "$KSHA")
echo "== building with KECK_ETCS_GIT_SHAS=$SHAS"
docker build -f "$STAGE/keck-etcs/nautilus/Dockerfile" \
  --build-arg "PYPEIT_SHA=$PIN" --build-arg "KECK_ETCS_GIT_SHAS=$SHAS" \
  -t "$IMAGE:$TAG" -t "$IMAGE:latest" "$STAGE"

# --- 4. smoke tests (bounded)
echo "== smoke tests"
run() { timeout 300 docker run --rm "$IMAGE:$TAG" "$@"; }
run python -c "import pypeit, keck_etcs; from keck_etcs import provenance; \
print('pypeit', pypeit.__version__, '| keck_etcs', keck_etcs.__version__, provenance.git_shas())"
run bash -lc 'python scripts/check_pypeit_pin.py --json /tmp/p.json | tail -1'
run bash -lc 'ls "$XDG_CACHE_HOME/pypeit" && du -sh "$XDG_CACHE_HOME/pypeit"'
run bash -lc 'run_pypeit --help | head -3'
SIZE=$(docker image inspect --format '{{.Size}}' "$IMAGE:$TAG")
echo "== image size: $(python3 -c "print(f'{$SIZE / 1e9:.2f} GB')")"
docker run --rm "$IMAGE:$TAG" pip list 2>/dev/null | grep -i -E '^(torch|nvidia|tensorflow|jax)' \
  && echo "WARNING: heavy ML packages present" || echo "   no torch/nvidia/tensorflow/jax"

# --- 5. push
if [[ $PUSH -eq 1 ]]; then
  echo "== pushing (if a push stalls >10 min on 'Waiting' or the manifest, interrupt and re-run)"
  echo "   using the Docker config $PUSH_DOCKER_CONFIG"
  DOCKER_CONFIG="$PUSH_DOCKER_CONFIG" docker push "$IMAGE:$TAG"
  DOCKER_CONFIG="$PUSH_DOCKER_CONFIG" docker push "$IMAGE:latest"
  DOCKER_CONFIG="$PUSH_DOCKER_CONFIG" docker manifest inspect "$IMAGE:$TAG" > /dev/null && echo "push OK: $IMAGE:$TAG"
  echo "digest: $(docker image inspect --format '{{join .RepoDigests " "}}' "$IMAGE:$TAG")"
fi
