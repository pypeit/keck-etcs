# keck-etcs image for Nautilus (design D31, section 4.8.2): PypeIt at the pinned
# develop commit, keck_etcs, and a populated PypeIt cache (MOSFIRE GitHub data
# plus the TellPCA telluric grid), so pods never download calibration data.
#
# Build it from the staging context written by nautilus/build_image.sh, which
# holds keck-etcs/ (this repo, without .git) and pypeit_requirements.txt (the
# dependencies of PypeIt at the pin):
#   bash nautilus/build_image.sh            # build + smoke tests
#   bash nautilus/build_image.sh --push     # ... then push and inspect the manifest
#
# The image is PUBLIC: nothing secret goes in (no S3 keys, no .netrc). Pods get
# S3 credentials only from the mounted secret (D32). No ENTRYPOINT: job
# manifests run `bash -lc` with the scripts under /opt/src/keck-etcs/scripts.
FROM python:3.12

ENV MPLBACKEND=Agg PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 QT_QPA_PLATFORM=offscreen
RUN pip install --upgrade pip

# ---------------------------------------------------------------------------
# LAYER 1 -- third-party dependencies only, before any COPY of our source, so
# a keck_etcs edit does not reinstall the scientific stack. Only the two
# requirement lists are copied. keck-etcs' requirements.txt names `pypeit`
# (the PyPI release); drop it, PypeIt comes from the pinned commit in layer 2.
# boto3 is for scripts/nautilus/s3_sync.py inside pods.
# ---------------------------------------------------------------------------
COPY pypeit_requirements.txt /opt/deps/pypeit_requirements.txt
COPY keck-etcs/requirements.txt /opt/deps/keck_etcs_requirements.txt
RUN sed -i '/^[[:space:]]*pypeit[[:space:]]*$/d' /opt/deps/keck_etcs_requirements.txt \
 && pip install -r /opt/deps/pypeit_requirements.txt -r /opt/deps/keck_etcs_requirements.txt \
      boto3 PyYAML

# ---------------------------------------------------------------------------
# LAYER 2 -- PypeIt at the pin (nautilus/pypeit_pin.txt). pip clones the full
# history, so setuptools_scm gives the usual 2.0.2.devN+g<sha> version.
# ---------------------------------------------------------------------------
ARG PYPEIT_SHA
RUN test -n "${PYPEIT_SHA}" || { echo "PYPEIT_SHA build arg is required"; exit 1; } \
 && pip install "git+https://github.com/pypeit/PypeIt.git@${PYPEIT_SHA}" \
 && python -c "import pypeit, os; v = pypeit.__version__; s = os.environ['PYPEIT_SHA']; \
g = v.split('+g')[-1].split('.')[0]; assert '+g' in v and s.startswith(g), (v, s); print('PYPEIT OK', v, s)"

# ---------------------------------------------------------------------------
# LAYER 3 -- the PypeIt cache (astropy >= 8 puts it at $XDG_CACHE_HOME/pypeit).
# Depends only on PypeIt and the grid checksum, so it sits before our source.
# The telluric grid is fetched from the public Nautilus URL, checked against
# the sha256 recorded in part 1 (nautilus/telluric_grid.sha256), and installed
# from the local file, so the cache holds exactly the verified bytes.
# NOTE: pypeit_cache_github_data fetches from PypeIt's GitHub `develop` branch
# at build time, not from the pinned commit.
# ---------------------------------------------------------------------------
ENV XDG_CACHE_HOME=/opt/cache
ARG TELGRID=TellPCA_3000_26000_R10000.fits
COPY keck-etcs/nautilus/telluric_grid.sha256 /opt/deps/telluric_grid.sha256
RUN mkdir -p "${XDG_CACHE_HOME}/pypeit" \
 && pypeit_cache_github_data keck_mosfire \
 && curl -fsSL -o "/tmp/${TELGRID}" \
      "https://s3-west.nrp-nautilus.io/pypeit/telluric/atm_grids/${TELGRID}" \
 && echo "$(cat /opt/deps/telluric_grid.sha256)  /tmp/${TELGRID}" | sha256sum -c - \
 && pypeit_install_telluric --local_file "/tmp/${TELGRID}" \
 && rm -f "/tmp/${TELGRID}" \
 && python -c "from pypeit.pkg import cache; h = cache.search_cache('${TELGRID}'); \
assert h, 'telluric grid not in the cache'; print('TELGRID OK', h)"

# ---------------------------------------------------------------------------
# LAYER 4 -- our code. The source stays at /opt/src/keck-etcs so the scripts/
# and nautilus/ files are available to job manifests.
# ---------------------------------------------------------------------------
COPY keck-etcs/ /opt/src/keck-etcs/
RUN pip install /opt/src/keck-etcs

# Source revisions, as JSON {"pypeit": ..., "keck_etcs": ...}. Declared this
# late on purpose: an ARG is part of the cache key of every later RUN, so
# declaring it earlier would rebuild layers 1-3 on every commit.
# keck_etcs.provenance.git_shas() prefers this over `git rev-parse` (no .git here).
ARG KECK_ETCS_GIT_SHAS="{}"
ENV KECK_ETCS_GIT_SHAS=${KECK_ETCS_GIT_SHAS}
LABEL org.opencontainers.image.revision="${KECK_ETCS_GIT_SHAS}" \
      org.opencontainers.image.source="https://github.com/pypeit/keck-etcs"

WORKDIR /opt/src/keck-etcs

# ---------------------------------------------------------------------------
# Build guards: any failure fails the build.
# (import keck_etcs.calib.harvest: added with S6, from image 0.1.5.)
# ---------------------------------------------------------------------------
RUN python -c "import json, os, pypeit; sh = json.loads(os.environ['KECK_ETCS_GIT_SHAS']); \
assert set(sh) >= {'pypeit', 'keck_etcs'} and 'unknown' not in sh.values(), sh; \
assert sh['pypeit'] == os.environ['PYPEIT_SHA'], (sh, os.environ['PYPEIT_SHA']); \
g = pypeit.__version__.split('+g')[-1].split('.')[0]; assert sh['pypeit'].startswith(g), pypeit.__version__; \
print('SHAS OK', sh, pypeit.__version__)" \
 && python -c "from pypeit.pkg import cache; assert cache.search_cache('TellPCA'), 'no TellPCA in cache'; print('CACHE OK')" \
 && run_pypeit --help > /dev/null && pypeit_sensfunc --help > /dev/null && pypeit_setup --help > /dev/null \
 && python -c "import keck_etcs, os; from keck_etcs import paths, provenance; \
d = os.path.join(os.path.dirname(keck_etcs.__file__), 'data'); \
[os.path.exists(os.path.join(d, f)) or (_ for _ in ()).throw(AssertionError(f)) for f in \
('index.yaml', 'sky/gemini_mk_sky_grid.fits', 'pypeit_par/keck_mosfire_J.sens')]; \
assert 'unknown' not in provenance.git_shas().values(), provenance.git_shas(); \
print('KECK_ETCS OK', keck_etcs.__version__, provenance.git_shas())" \
 && python scripts/check_pypeit_pin.py --json /tmp/pin_check.json \
 && python scripts/mosfire/reduce_standard.py --help > /dev/null \
 && python scripts/nautilus/s3_sync.py --help > /dev/null \
 && python nautilus/gates.py --help > /dev/null && python nautilus/status_row.py --help > /dev/null \
 && python scripts/mosfire/build_sensfunc.py --help > /dev/null \
 && python -c "import keck_etcs.calib.harvest, keck_etcs.calib.monitor, keck_etcs.calib.monitor_configs" \
 && python scripts/mosfire/harvest_sens.py --help > /dev/null \
 && echo "GUARDS OK"
