# Keck MOSFIRE implementation, part 7: the ETC on Read the Docs (Phase 6)

## Goals

Describe and host the MOSFIRE ETC on readthedocs.org. Steps:

1. **Build** Sphinx documentation for `keck_etcs` from the existing
   documents, the code and the JSON schemas.
2. **Add** a reference generated from the schemas and executed examples.
3. **Add** an interactive ETC page that runs `keck_etcs.etc.compute`
   in the reader's browser (Pyodide), so Read the Docs serves a working
   calculator without a server.
4. **Publish** it as a Read the Docs project that rebuilds on every push and
   carries the calibration version.

These are new plan steps S19-S22, after the MOSFIRE J milestone (part 6).
WMKO's own hosted front end (design D11, 1) stays theirs. This doc gives the
community a documented, citable and usable ETC in the meantime, and gives
WMKO a reference implementation.

Run order: S19 -> S20 -> S21 -> S22. S21 is independent of S20 once S19
exists, and can be dropped if the user answers no to the Q&A item below
(S22 then publishes the documentation only). Part 6 must be complete; it
is.

## Context

- **The ETC exists** (part 6, prompt #4):
  - entry point `keck_etcs/etc.py`, `compute(inputs: dict) -> dict` and
    `validate`;
  - physics `keck_etcs/core/`; instrument `keck_etcs/instruments/mosfire.py`;
  - schemas `keck_etcs/schema/etc_input.json` and `etc_output.json`;
  - CLI `bin/keck_etc`; example inputs `examples/*.json`;
  - calibration release `mosfire-J-2026.10` under `keck_etcs/data/`
    (`index.yaml`).
- **The ETC is light.** `compute()` imports only numpy, scipy, astropy,
  jsonschema and pyyaml (`setup.py` `install_requires`; S18). A wheel built
  from the repo carries all 40 data files, about 3 MB of them the Gemini sky
  grid. PypeIt, matplotlib and boto3 are in the `calib` extra and must not
  be needed to build the documentation; mock them for autodoc if
  `keck_etcs.calib` is documented. `keck_etcs/tests/test_core_imports.py`
  already checks that `keck_etcs.core` imports without them.
- **Existing documents to reuse, not duplicate:**
  - `README.md` (install, usage, data root, monitor, refreshing
    calibrations);
  - `docs/wmko_api_note.md` (every field, units, defaults, errors, versions);
  - `docs/keck_mosfire_design.md` (design, v0.5);
  - `reports/Keck_MOSFIRE_report_20261009.md` (results, with figures in
    `reports/figures/` and `docs/figures/`);
  - `CHANGES.md`;
  - `nautilus/README.md` (operator guide; developer-facing);
  - `docs/XTcalc_bug.md`, `docs/XTcalc_HOWTO.md`.

  All are Markdown, so the Sphinx build should use MyST (`myst-parser`, or
  `myst-nb` if examples are executed as notebooks) and include these files
  rather than copy them. `scripts/check_docs.py` already checks the README
  examples, the WMKO note against the schemas, and version agreement;
  extend it rather than add a parallel checker.
- **Repository:** `https://github.com/pypeit/keck-etcs`, **public**, default
  branch `main`. The MOSFIRE work is on branch `keck-mosfire`, which is not
  yet merged. Read the Docs builds `main` as `latest` by default; which
  branch or tag it should build is a question for the user (Q&A).
- **Read the Docs** (readthedocs.org, the free community site for public
  repositories):
  - a `.readthedocs.yaml` (version 2) at the repo root names the OS, the
    Python version, the Sphinx `conf.py` and the install steps (a docs
    requirements file plus `pip install .`);
  - builds run on RTD's machines with time and memory limits. Check the
    current limits in RTD's documentation; do not rely on memory;
  - "versions" map to branches and tags; `latest` and `stable` are
    automatic; pull-request previews are optional;
  - creating the project (importing the GitHub repo, which installs a
    webhook) is done by the user in their RTD account. It is
    outward-facing; the session prepares everything and gives the steps.
- **Pyodide** (for S21) runs CPython in the browser from a CDN. Its
  distribution includes numpy, scipy and pyyaml, and probably astropy;
  pure-Python wheels install with `micropip`. Verify each dependency of
  `compute()` against the current Pyodide package list before building on
  it:
  - astropy;
  - jsonschema and its compiled dependency `rpds-py` (through
    `referencing`).

  If one is missing, the options are a pinned older pure-Python version, or
  a fallback in `keck_etcs.schema` that validates without jsonschema in the
  browser only. The latter is a code change: ask first.

  The page loads a `keck_etcs` wheel built during the RTD build and served
  as a static file next to the HTML. Only static files are hosted; there is
  no server.
- **Versions on every page:** each page should show `keck_etcs.__version__`
  and the calibration version (from `keck_etcs/data/index.yaml`), and the
  interactive page should echo `meta.calib_version` and `meta.era` from
  the actual `compute()` output, so a reader always knows which
  calibration produced a number.
- **Rules (CLAUDE.md):**
  - the user runs git (including any merge to `main` and any tag), creates
    the RTD project and changes its settings;
  - Python runs in `conda run -n pypeit14b` on the workstation;
  - calculations and generators are scripts on disk;
  - no secret value in any file (RTD needs none for a public repo);
  - log each prompt.
  - New Python dependencies go only in a docs requirements file (e.g.
    `docs/requirements.txt`), never in `install_requires`. Install them in
    `pypeit14b` only with the user's go-ahead, or build in a scratch venv.

## Prompts

0. **Q&A**  I have answered your first round of questions in the Q&A section below.
   Let me know if you have any others.
   Use Opus 5.5 and log your work.

1. **S19: Sphinx skeleton, local build.**
   - **Files:** add a Sphinx project under `docs/` (`conf.py`, `index.md`)
     that sits beside the existing Markdown documents without moving them.
     Add `docs/requirements.txt` (Sphinx, a theme, `myst-parser`, versions
     pinned) and `.readthedocs.yaml`.
   - **Pages** (MyST includes of the files in Context, not copies; fix
     relative image paths so the report's figures render):
     - "Getting started", from `README.md` usage;
     - "API for WMKO", from `docs/wmko_api_note.md`;
     - "Results", from the report;
     - "Design";
     - "Release notes", from `CHANGES.md`;
     - "Developer: Nautilus operator guide".
   - **API reference:** autodoc of `keck_etcs.etc`, `keck_etcs.core.*` and
     `keck_etcs.instruments.*`, with napoleon for the Google-style
     docstrings. `keck_etcs.calib` only if it builds with PypeIt and
     matplotlib mocked.
   - **Version line:** a version and calibration line on every page,
     computed in `conf.py` from `keck_etcs.__version__` and `index.yaml`.
   - **Build:** locally with `sphinx-build -W --keep-going -b html docs
     docs/_build/html` in a scratch venv, or in `pypeit14b` after the
     user's go-ahead. Add `docs/_build/` to `.gitignore`.
   - **Verify:**
     - the build passes with `-W` (warnings are errors);
     - every page in the toctree renders, and every image in the report
       page is found (a link-check pass, `-b linkcheck`, for internal links
       only, or a script on disk);
     - the version line shows `0.2.5` / `mosfire-J-2026.10`;
     - the build environment has no PypeIt (prove it: print `pip list` in
       the build log, or import-check in `conf.py`).
   - Log your work, with the build time and the page list.

2. **S20: schema reference and executed examples.**
   - **Field reference:** write a small generator (a script on disk, called
     from `conf.py` at build time) that turns `etc_input.json` and
     `etc_output.json` into Markdown tables. Each table has field (dotted
     path), type, range or enum, default, unit (`x-unit`) and description.
     It becomes an "ETC field reference" page that cannot drift from the
     schemas. Keep `docs/wmko_api_note.md` as the one-page summary, and
     link the two.
   - **Examples:** add an "Examples" page that *executes* `compute()` at
     build time and shows the results:
     - the three `examples/*.json` inputs;
     - a J = 20 AB point source (S/N against wavelength, with sky);
     - exposure time against magnitude for J and J2 (S/N 5 per resolution
       element);
     - a line-flux case;
     - the `throughput.date` era selection.

     Use `myst-nb` with a notebook stored *without* outputs, or the
     matplotlib `plot` directive; pick one and say why. matplotlib then
     becomes a docs-only requirement. The numbers on the page must come
     from the build, not be pasted.
   - **Checks:** extend `scripts/check_docs.py` so that the generated field
     tables list every leaf field of both schemas, the same set it already
     checks for the WMKO note.
   - **Verify:**
     - `-W` build passes;
     - the field reference lists 31 input and 36 output fields;
     - the example page's J = 20 AB band-median S/N equals `compute()` run
       in `pypeit14b` (4.473 per pixel at the defaults, latest era) to 1e-6;
     - the RTD build time stays well inside its limit (record it).
   - Log your work.

3. **S21: interactive ETC page (Pyodide), if the Q&A says yes.**
   - **Feasibility first.** Check the current Pyodide release's package
     list for numpy, scipy, astropy, pyyaml, jsonschema and their
     dependencies, and record the version found. Build the `keck_etcs`
     wheel (`pip wheel --no-deps .`), load it in a local Pyodide (the
     Pyodide CDN in a browser page served by `python -m http.server`, or
     Pyodide's Node.js runner), and run `compute({})`. Compare its summary
     with the CPython result. Report the load time and the download size
     (Pyodide plus the packages plus the wheel); if it is impractical (for
     example tens of MB or tens of seconds), stop and report before
     building the page.
   - **The page:** `docs/etc.md`, with raw HTML and JS, or a small
     Sphinx extension. It has:
     - a form for the main inputs, with defaults and ranges taken from
       `etc_input.json` at build time: band, slit width, source type and
       magnitude (AB/Vega), spectrum shape (flat f_nu, power law, line with
       wavelength, flux and width), seeing, exposure per frame, frames,
       readout, nod, airmass, PWV, `sky_scale`, `throughput.date`, and
       target S/N with its reference;
     - a "Compute" button that calls `compute()` in Pyodide;
     - the summary (S/N per pixel and per resolution element, exposure
       time, saturation flag), every warning verbatim, the versions
       (`meta.keck_etcs_version`, `meta.calib_version`, `meta.era`), a
       plot of S/N per pixel against wavelength with the sky, and a
       "download JSON" link for the full output and the inputs.

     Schema errors (`InputError`) are shown as messages, not stack traces.
     Plotting can be a light JS library from a CDN, or matplotlib in
     Pyodide; choose the smaller load.
   - **Build:** the wheel is built in the RTD build (`.readthedocs.yaml`
     build jobs, or a `conf.py` step) and copied to `_static/` with its
     version in the file name, so the page and the docs can never disagree.
     Pin the Pyodide version.
   - **Verify:**
     - in Chrome and Firefox (locally served build), the default inputs
       give the same `snr_pixel_median` as CPython to 1e-6;
     - an invalid input (slit 10") shows the schema message;
     - a `target_snr` case matches CPython's solved exposure time;
     - the page states the calibration version;
     - first-load time and size are recorded;
     - the page works offline after the first load only if the browser
       cache allows; no claim beyond that.
   - Log your work, with screenshots saved under `docs/_static/` only if
     the user wants them committed.

4. **S22: publish on Read the Docs.**
   - **Before the user imports the project:**
     - `.readthedocs.yaml` final (OS, Python 3.12, `docs/requirements.txt`,
       `pip install .` without extras, the S21 wheel step if any,
       `fail_on_warning: true`);
     - a `docs` badge and the RTD URL in `README.md`, with the URL marked
       "pending" until the project exists;
     - a short "Citing and versions" page: how the code and calibration
       versions appear, and that WMKO's front end will be the
       observatory's official tool.
   - **Give the user the exact steps:**
     - log in at readthedocs.org with GitHub;
     - import `pypeit/keck-etcs`;
     - the project slug (Q&A);
     - which branch builds `latest` (Q&A);
     - activate `stable` once a tag exists;
     - optionally enable pull-request previews.
   - **After the first build:** fetch the build log (from the RTD web page
     or its public API; read-only) and check:
     - no PypeIt installed;
     - build time;
     - no warnings.

     Then open the published pages and check that the version line, the
     field reference, the executed examples and (if S21) the interactive
     page work on the published site exactly as locally.
   - **Release process:** add an item to the release steps in `README.md`
     ("Refreshing calibrations") and `nautilus/README.md` section 10: a
     calibration release or code version bump triggers an RTD build, and the
     published version line must show the new tag. `scripts/check_docs.py`
     can check the local build; the published site is checked by hand or
     with a read-only fetch.
   - **Verify:**
     - the published `latest` (and `stable`, if a tag exists) shows
       keck_etcs 0.2.5 / `mosfire-J-2026.10`;
     - a push to the built branch triggers a rebuild (the user pushes; you
       watch the build list);
     - `check_docs.py` passes, with no secret in any new file.
   - Log your work, with the public URL and the build ids.

## Q&A

Please answer with ">A." lines before prompt #1 is run (a default is
proposed for each):

- **S19-1. Branch.** Which branch should Read the Docs build as `latest`?
  - (a) `main`, after the user merges `keck-mosfire` (recommended: `main`
    is the repository's default and the public face);
  - (b) `keck-mosfire` until the merge, then switch to `main`.
>A. Use (a), I will expose both
- **S19-2. Theme.** (a) `furo` (clean, good on mobile, dark mode;
  recommended); (b) `sphinx-rtd-theme` (the classic RTD look; PypeIt uses
  it); (c) `pydata-sphinx-theme`.
>A. Use (a), furo is the cleanest and most modern theme
- **S19-3. Scope of the public docs.** The Nautilus operator guide and the
  design's infrastructure sections describe a private bucket and the user's
  cluster workflow; they hold no secrets, but are they wanted on a public
  site?
  - (a) include them under a "Developer" section (recommended: they are
    already public in the GitHub repository);
  - (b) user-facing docs only (getting started, API, field reference,
    examples, results, release notes).
>A. (a)
- **S21-1. Interactive page.** Build the in-browser calculator (S21)?
  - (a) yes, if the feasibility check passes (recommended);
  - (b) no, documentation only; WMKO's front end comes later.
>A. (a)
- **S22-1. Project slug.** The RTD project name, which sets the URL
  `https://<slug>.readthedocs.io`: (a) `keck-etcs` (recommended);
  (b) other.
>A. (a)

Second round (prompt #0, 2026-10-10). Please answer with ">A." lines before
prompt #1:

- **S19-4. Build environment for Sphinx** (CLAUDE.md: nothing is installed in
  `pypeit14b` without a go-ahead):
  - (a) a new conda env `keck-etcs-docs` (Python 3.12, like the RTD build)
    with `pip install -r docs/requirements.txt` and `pip install .`, i.e.
    no PypeIt, as on RTD (recommended: it reproduces the RTD build and
    proves the docs need no PypeIt);
  - (b) a throw-away venv in the session scratchpad;
  - (c) install the docs requirements into `pypeit14b`.
>A. (c)
- **S22-2. Default version until the merge.** You will expose both `main`
  and `keck-mosfire` (S19-1). Today `origin/main` is the start-up merge
  (`987dca0`), 65 commits behind `keck-mosfire`, with no `keck_etcs/etc.py`,
  no `docs/` and no `.readthedocs.yaml`. Read the Docs will therefore fail
  to build `latest` (main) until the merge. Until then:
  - (a) make `keck-mosfire` the project's *default version* (what
    `https://keck-etcs.readthedocs.io/` opens) and leave `latest` inactive;
    switch the default to `latest` once `main` has the merge
    (recommended);
  - (b) activate both and accept a failed `latest` build until the merge.
>A. (b)
- **S21-2. Where the interactive page loads Pyodide from.** Each reader's
  browser downloads Pyodide and its packages when the page is opened.
  - (a) the official Pyodide CDN (jsDelivr), with an exact version pinned
    (recommended: no hosting cost, and browsers cache it). This is a
    third-party request, stated on the page.
  - (b) self-host the Pyodide files we need as static files on RTD: larger
    builds and repository-independent, but no third-party request.
>A. Try and go with (b)
- **S22-3. Citation (optional).** The repository has a BSD-3 `LICENSE` but no
  `CITATION.cff` or DOI.
  - (a) add a `CITATION.cff` now (authors, title, repository, license; no
    DOI), and leave a Zenodo DOI until the first tag after the merge
    (recommended);
  - (b) nothing for now.
>A. (a)

Third round (prompt #3, 2026-10-10; the S21 feasibility check stopped
here, as the prompt asks, because the cold download is "tens of MB"):

- **S21-3. Interactive page: size and loading.** In Chrome the first visit
  downloads **36.4 MB** (measured). That is Pyodide's core (12.3 MB), the
  ETC's 15 packages (25.8 MB: scipy 14.0, astropy plus IERS data 8.0, numpy
  3.0) and the 4.7 MB wheel, before compression savings. The browser caches
  it afterwards.
  - The first result appears after about 9 s on this workstation's
    connection: Pyodide 2.3 s, packages 4.7 s, wheel 5.2 s, first compute
    3.6 s. A later compute takes 0.02 s.
  - On a 20-50 Mbit/s home connection, expect roughly 10-20 s more for the
    download.
  - The results are exact: Pyodide equals CPython to 2e-16.

  Options:
  - (a) build the page as is, but load Pyodide only when the reader clicks
    "Start the calculator", with the size and time stated on the button, so
    the rest of the docs never pays for it (recommended: no code change, and
    results identical to the library);
  - (b) as (a), and also drop astropy from the browser path (-8 MB) by
    shipping the four tables `compute()` reads (throughput, filters,
    detector, sky grid) in a browser-only format. That is a code change in
    `keck_etcs/instruments/base.py`, which needs your approval;
  - (c) as (b), and also replace the five scipy functions on the compute
    path (`fftconvolve`, `simpson`, `beta`/`betainc`, `brentq`, `ndtr`) with
    numpy code (-14 MB, to about 14 MB in total). This is a larger change to
    validated physics and needs new regression checks;
  - (d) stop at documentation only.
>A. (a)

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs

### 2026-10-10 (Prompt #0: first-round answers read; second-round questions)

Model: Claude Opus 5.5.

**Answers recorded (round 1):**

- **S19-1:** (a) `main` builds `latest`, and the user will expose both
  `main` and `keck-mosfire`.
- **S19-2:** `furo`.
- **S19-3:** (a) include the developer pages (operator guide, design
  infrastructure) under "Developer".
- **S21-1:** (a) build the in-browser calculator if the feasibility check
  passes.
- **S22-1:** slug `keck-etcs`, i.e. `https://keck-etcs.readthedocs.io`.

**Checked (read-only) to find what remains open:**

- `origin/main` is the start-up merge `987dca0`, 65 commits behind
  `keck-mosfire`. It holds `.claude`, `.gitignore`, `CLAUDE.md`,
  `LICENSE`, `README.md`, `claude_prompts`, `keck_etcs` (start-up only),
  `pytest.ini`, `requirements.txt` and `setup.py`.
- So a `latest` build from `main` fails until the merge. This makes
  "expose both" a question of which version is the default (S22-2).
- `LICENSE` is BSD 3-Clause (2026, PypeIt); there is no `CITATION.cff`.
- Sphinx is not installed anywhere, so the build environment needs a
  decision (S19-4).

**Second-round questions** (added under Q&A, each with a recommended
default):

- S19-4: build environment (a new `keck-etcs-docs` conda env without
  PypeIt);
- S22-2: default version until the merge (`keck-mosfire` as default,
  `latest` inactive until then);
- S21-2: Pyodide from the pinned jsDelivr CDN or self-hosted (CDN);
- S22-3: `CITATION.cff` now, DOI later (optional).

None of these blocks the start of S19 except S19-4 (where to build).


### 2026-10-10 (Prompt #1 / S19: Sphinx skeleton, local -W build passes, no PypeIt)

Model: Claude Opus 5.5.

**Build environment.** The second-round Q&A (S19-4) is not answered yet.
Prompt #1 allows a scratch venv without a go-ahead, so I used a throw-away
conda env in the session scratchpad (`conda create -p <scratch>/docsenv
python=3.12`). Nothing was installed in `pypeit14b`. Answer S19-4 if you
want a persistent `keck-etcs-docs` env instead.

**Files.**

- **`docs/requirements.txt`:** sphinx 9.1.0, furo 2025.12.19,
  myst-parser 5.1.0, docutils 0.22.4, pinned; docs only.
- **`.readthedocs.yaml`:** version 2, ubuntu-24.04, Python 3.12,
  `docs/conf.py`, `fail_on_warning: true`; installs `docs/requirements.txt`
  and `pip install .` (no extras).
- **`docs/conf.py`:**
  - extensions: MyST, autodoc, napoleon (Google style), viewcode, mathjax;
  - theme furo (S19-2);
  - **the version line** "keck_etcs 0.2.5 · calibration
    mosfire-J-2026.10 · MOSFIRE J/J2" is furo's `announcement` bar, so it
    appears on every page. It is computed from the *installed*
    `keck_etcs.__version__` and its `data/index.yaml`;
  - `source_branch` follows `READTHEDOCS_GIT_IDENTIFIER`;
  - `autodoc_mock_imports` covers pypeit, matplotlib, boto3 and IPython;
  - **the no-PypeIt proof:** it prints `pip list` and whether PypeIt is
    importable into the build log, and stops the build if PypeIt is present
    (override with `KECK_ETCS_DOCS_ALLOW_PYPEIT=1` for a local preview).
- **Pages.** The existing Markdown files are included or used directly,
  never copied:
  - `index.md`: an introduction and three toctrees ("Using the ETC",
    "Calibration and validation", "Developer");
  - `getting_started.md`: includes `README.md` from Installation to before
    Layout (installation, usage, data root, monitor, refreshing
    calibrations);
  - `wmko_api_note.md`, `keck_mosfire_design.md`,
    `keck_mosfire_implementation.md`, `XTcalc_bug.md` and `XTcalc_HOWTO.md`
    are already in `docs/` and are used directly;
  - `results.md` includes the report, and `changes.md` includes
    `CHANGES.md`;
  - `developer/nautilus.md` includes `nautilus/README.md`, under
    "Developer" (S19-3);
  - `api/index.md`, `api/etc.md`, `api/core.md` (7 modules),
    `api/instruments.md` (base, mosfire) and `api/calib.md` (standards,
    harvest, combine, trend, monitor; built with PypeIt mocked).
- **`scripts/check_docs_build.py` (new; standard library only)** checks the
  built tree:
  - all 15 pages exist;
  - every page has the version line with the repository's version and
    calibration;
  - every `<img>` and relative link resolves;
  - the report page has as many images as the report's Markdown;
  - the API pages hold `compute`, `validate`, `core.snr`,
    `core.lsf.fwhm_pix`, `instruments.mosfire` and `calib.combine_era`.

**Build:**
`sphinx-build -W --keep-going -b html docs docs/_build/html`.

- The first run gave 4 warnings: `:heading-offset: 1` on the README include
  made H1 → H3 jumps. Removed.
- The second run: **build succeeded, 0 warnings, 5.0 s wall-clock**
  (`docs/_build/` was already git-ignored).

**Verify.**

- **The `-W` build passes.**
- **No PypeIt:** the log says "PypeIt importable in the build environment:
  False", and its `pip list` has keck_etcs 0.2.5, numpy 2.5.3, scipy
  1.18.1, astropy 8.0.1, jsonschema 4.26.0, PyYAML 6.0.3 and no pypeit.
- **`check_docs_build.py`: ALL CHECKS PASS.**
  - 15 pages, all with the version line "0.2.5 / mosfire-J-2026.10".
  - 11 images (9 in the report, including the 5 under `docs/figures/`
    reached through `:relative-images:`, and 2 in XTcalc_bug) and 411
    internal links resolve.
  - The report shows 9 of 9 images.
  - The API objects are present.
- **`check_docs.py`** (`pypeit14b`): ALL CHECKS PASS; the secret scan now
  covers 205 files.

**Page list (15):**

- `index`, `getting_started`, `wmko_api_note`, `results`, `changes`;
- `keck_mosfire_design`, `developer/nautilus`,
  `keck_mosfire_implementation`, `XTcalc_bug`, `XTcalc_HOWTO`;
- `api/index`, `api/etc`, `api/core`, `api/instruments`, `api/calib`.

**What I learned.**

- MyST's `{include}` with `:relative-images:` rewrites image paths relative
  to the including page. Sphinx copies images from outside `docs/`
  (`reports/figures/`) into `_images/`, so the report's figures need no
  copy.
- The docstrings build cleanly under napoleon with `-W`; nothing needed
  fixing.
- Sphinx module anchors are `module-<name>`.

**Files for the user to commit:**

- `.readthedocs.yaml`;
- `docs/conf.py`, `docs/requirements.txt`, `docs/index.md`,
  `docs/getting_started.md`, `docs/results.md`, `docs/changes.md`;
- `docs/developer/nautilus.md`, `docs/api/{index,etc,core,instruments,calib}.md`;
- `scripts/check_docs_build.py`;
- this prompt doc.

### 2026-10-10 (Prompt #2 / S20: generated field reference, executed examples; -W build in 9 s)

Model: Claude Opus 5.5. The second-round Q&A is still unanswered, so the
build ran again in the scratch env (S19-4 (b)), with nothing installed in
`pypeit14b`.

**Field reference.**

- **`scripts/gen_field_reference.py` (new; standard library):** walks both
  schemas and resolves `$defs`/`$ref` and `anyOf`. It writes one row per
  leaf field: dotted path, type, range or enum (min, max, exclusive min,
  pattern, item and length constraints), default (JSON), `x-unit`, and the
  description, marked *(required)* or *(always present)*.
- **`docs/conf.py`** calls `gen_field_reference.write()` at every build,
  into `docs/_generated/field_reference_tables.md`. That file is
  git-ignored and excluded as a page; it is written only when its content
  changes.
- **`docs/field_reference.md`** includes it: 31 input and 36 output rows.
- **The WMKO note and the reference link to each other:** the note's header
  links to the reference, and the reference links back to the note.

**Examples: myst-nb, chosen over the matplotlib `plot` directive.** The
plot directive renders only figures; the printed numbers would then need a
second generator. A MyST *text* notebook (`docs/examples.md`, `file_format:
mystnb`) runs in a Jupyter kernel at build time and shows both the code and
its real output. Kept as Markdown it can never hold stored outputs, and it
diffs cleanly in git.

- **Settings:** `nb_execution_mode = 'force'` (always executed),
  `nb_execution_raise_on_error = True` (a failing cell fails the build),
  300 s timeout.
- **Cells:**
  - the versions;
  - the three `examples/*.json`: S/N per pixel and per resel, line S/N,
    frames, saturation flag, number of warnings;
  - J = 20 AB at the defaults: the exact `snr_pixel_median` and
    `snr_resel_median`, slit and aperture fractions, the warnings, and a
    figure of S/N against wavelength with the sky;
  - exposure time against magnitude for J and J2 (S/N 5 per resel,
    8 frames), printed and plotted;
  - a 1e-17 erg/s/cm^2 line at 12820 A (`snr_line` and window, plotted);
  - `throughput.date` selecting each era.
- **Seen in the output:** J2 at 23 AB solves to 5479 s per frame, above the
  3600 s maximum, and `compute()` warns. That is the intended behaviour,
  shown as is.

**Dependencies.**

- `docs/requirements.txt` adds myst-nb 1.4.0, ipykernel 7.4.0 and
  matplotlib 3.11.2, pinned; myst-parser stays 5.1.0.
- `conf.py` now loads `myst_nb`, which includes myst-parser, with `.md`
  mapped to `myst-nb`.
- `.gitignore` adds `docs/_generated/` and `docs/jupyter_execute/`.
- matplotlib stays docs-only: it is in the `calib` extra and the docs
  requirements, never in `install_requires`.

**Checks extended.**

- **`scripts/check_docs.py`:**
  - check 6: the generated tables list exactly the leaf fields of both
    schemas, the same walker as the WMKO-note check;
  - check 7: if `docs/_build/html/examples.html` exists, its printed J = 20
    AB `snr_pixel_median` equals `compute()` in the running environment to
    1e-6.
- **`scripts/check_docs_build.py`** now expects 17 pages, adding `examples`
  and `field_reference`.

**Verify.**

- **`-W` build passes:** "build succeeded", 0 warnings; the notebook ran in
  3.3 s. The kernel's "TCP without encryption" line is a log message, not a
  Sphinx warning.
- **The field reference lists 31 input and 36 output fields**
  (`check_docs.py` check 6 OK).
- **The examples page agrees with `pypeit14b`:** it prints
  `snr_pixel_median = 4.47275798416922`, identical to `compute()` in
  `pypeit14b` (check 7: relative difference 0).
- **`check_docs_build.py`: ALL CHECKS PASS.** 17 pages with the version
  line; 14 images and 491 internal links resolve.
- **`check_docs.py`: ALL CHECKS PASS** (secret scan of 208 files).
- **Build time against the RTD limit.** Read the Docs' build
  documentation, fetched today, gives 15 minutes and 7 GB of memory for
  Community projects. Simulated in a fresh venv from the same Python:
  - cold `pip install --no-cache-dir -r docs/requirements.txt .`: 25.5 s;
  - `sphinx-build -W`: 8.2 s;
  - peak memory of the Sphinx process 0.22 GB (the notebook kernel is a
    separate, light process).

  That is about 34 s against 900 s. RTD's own overhead (clone, environment
  set-up) will add to it; the margin is large.

**Files for the user to commit:**

- new: `scripts/gen_field_reference.py`, `docs/field_reference.md`,
  `docs/examples.md`;
- modified: `docs/conf.py`, `docs/requirements.txt`, `docs/index.md`,
  `docs/wmko_api_note.md` (the link), `.gitignore`,
  `scripts/check_docs.py`, `scripts/check_docs_build.py`, this prompt doc.

### 2026-10-10 (Prompt #3 / S21: Pyodide feasibility. Exact, but 36 MB on first load; stopped for the S21-3 decision)

Model: Claude Opus 5.5. The second-round Q&A is still unanswered.

- S21-2 takes its recommended default (a), Pyodide from the pinned jsDelivr
  CDN, for the feasibility test only.
- The scratch env is reused (S19-4 (b)); nothing was installed in
  `pypeit14b`.
- Playwright 1.63.0 is installed in the scratch env only, driving the
  system Google Chrome. No browser was downloaded.

**Pyodide version and packages.** The latest Pyodide on npm is **314.0.7**
(Python 3.14.2, ABI 2026_0). Its `pyodide-lock.json` has every dependency
of `compute()`:

- numpy 2.4.6, scipy 1.18.0, pyyaml 6.0.3;
- astropy 7.2.0, with pyerfa, astropy-iers-data and packaging;
- jsonschema 4.26.0, with referencing, compiled `rpds-py` 0.30.0, attrs,
  jsonschema-specifications and pyrsistent.

matplotlib 3.10.8 is also available, but it adds 10.2 MB; a JS plot is
lighter.

**Download size** (jsDelivr `Content-Length`):

- Pyodide core: 12.28 MB (`pyodide.asm.wasm` 9.60, `python_stdlib.zip`
  2.55);
- the closure of the ETC's dependencies: 15 packages, 25.81 MB. scipy 14.03,
  astropy 5.99, astropy-iers-data 1.99 and numpy 2.96 dominate;
- our wheel: 4.67 MB;
- total about 42.8 MB of files; the browser measured 36.4 MB transferred.

**Run in headless Chrome 149.** The new script `scripts/pyodide_check.py`
writes a test page, serves it on localhost and loads Pyodide from the CDN.
It installs the wheel with micropip and compares three cases with CPython:

| Case | Pyodide | CPython | Result |
|---|---|---|---|
| `compute({})`: `snr_pixel_median` | 4.4727579841692195 | 4.47275798416922 | rel 2e-16, OK |
| J2 21 AB, `target_snr` 5/resel: `exptime_s` | 237.07418038007444 | 237.07418038007478 | rel 1e-15, OK |
| slit 10": `InputError` message | identical: "slit_width_arcsec: 10.0 is greater than the maximum of 5.0" | | OK |

- The versions echoed are keck_etcs 0.2.5, calibration `mosfire-J-2026.10`
  and era 2025-04.., the same warnings as CPython.
- **Timing (cold, fresh profile):** Pyodide ready 2.3 s, packages 4.7 s,
  wheel 5.2 s, then the first `compute` 3.6 s (it reads the sky grid and
  the tables). Subsequent calls take 0.02 s.
- **Total:** about 9 s to the first result, 36.4 MB transferred.

**Decision needed.** The prompt says to stop and report if the cost is
"tens of MB or tens of seconds". 36 MB is in that range, although the time
on this connection (9 s) is not. The options and a recommendation are in
Q&A S21-3. Nothing has been built for the page yet.

- The scipy and astropy uses on the compute path are real, so shrinking
  needs code changes:
  - `core/lsf` fftconvolve;
  - `core/slitloss` simpson, beta and betainc;
  - `core/snr` brentq;
  - `core/source` ndtr;
  - `instruments/base` astropy Table and fits.
- Firefox is not tested yet. It needs Playwright's own Firefox build, a
  download of about 100 MB into the scratch env, and is planned for the
  page-verification stage.

**Read the Docs status** (public API, read-only, 2026-10-10):

- **Project `keck-etcs`:** builds 35063949 (45 s) and 35063962 (77 s) of
  `keck-mosfire` succeeded, and https://keck-etcs.readthedocs.io/en/keck-mosfire/
  serves.
- **`latest`:** build 35063843 (`main`) failed, as expected, since `main`
  has no docs configuration.
- **The default version is still `latest`**, so
  https://keck-etcs.readthedocs.io/ redirects to a 404 `/en/latest/`. Set
  Admin → Settings → Default version to `keck-mosfire` (S22-2 (a)), and
  deactivate or hide `latest` until the merge.

**Files:** new `scripts/pyodide_check.py`, plus this prompt doc.


### 2026-10-10 (Prompt #4: S21 interactive page built, self-hosted, verified in Chrome and Firefox; S22 pre-publish done; waiting for the push)

Model: Claude Opus 5.5.

**Answers read.**

- S19-4 (c): install the docs requirements in `pypeit14b`.
- S22-2 (b): both versions active; a failed `latest` is accepted until the
  merge.
- S21-2 (b): self-host Pyodide.
- S22-3 (a): `CITATION.cff` now.
- S21-3 (a): build the page, loading Pyodide on demand.

S22 publishes the interactive page, so this prompt first finished S21 on
those answers, then did S22's pre-publish items. S22's post-push checks
wait for the user's commit and push.

**`pypeit14b` and the pins (S19-4 (c)).**

- A dry run showed the first pins would upgrade Sphinx 8.2.3 to 9.1.0,
  docutils 0.21.2 to 0.22.4 and matplotlib 3.11.0 to 3.11.2.
- PypeIt's own docs stack (`sphinx-rtd-theme` 3.0.0, its `docs` extra)
  needs `sphinx<9` and `docutils<0.22`.
- `docs/requirements.txt` is therefore re-pinned to sphinx 8.2.3,
  docutils 0.21.2 and matplotlib 3.11.0, as already in `pypeit14b`; furo
  needs sphinx >= 7 and myst-parser 5.1 needs >= 8.
- The install into `pypeit14b` then only *added* packages (myst-nb,
  myst-parser, furo, ipykernel, jupyter-cache and their dependencies).
  `pip check`: no broken requirements.
- A local build in `pypeit14b` needs `KECK_ETCS_DOCS_ALLOW_PYPEIT=1`, since
  `conf.py` refuses PypeIt by default. Read the Docs proves the build works
  without PypeIt.

**S21: self-hosted Pyodide.**

- **`scripts/fetch_pyodide.py` (new; standard library)** downloads, at
  build time, exactly the files a browser requested in the measurement
  run: 5 core files (`pyodide.js`, `pyodide.asm.mjs`, `pyodide.asm.wasm`,
  `python_stdlib.zip`, `pyodide-lock.json`) and the 16 wheels of
  numpy/scipy/astropy/pyyaml/jsonschema/micropip and their dependencies.
  - Core files are checked against the committed
    `docs/pyodide_core.sha256`, written by `--record`, the one step that
    trusts the CDN.
  - Wheels are checked against the sha256 in the verified lock file.
  - Pinned to Pyodide 314.0.7: 39.5 MB, kept in
    `docs/_generated/static/pyodide/` (git-ignored); present files are
    reused.
- **`docs/conf.py`** runs it at every build. It also builds the wheel of the
  same source tree (`pip wheel --no-deps`), copies `etc_input.json`, and
  writes `etc_config.json` (Pyodide version and Python, the wheel's name
  with its version, keck_etcs and calibration versions, first-load size).
  All of it is served under `_static/`.
- **`docs/etc.md`** ("Interactive calculator", first in "Using the ETC") with
  **`docs/_static/etc.js` and `etc.css`**, plain JS with no third-party
  library:
  - nothing loads until "Start the calculator (downloads about 44 MB
    once, from this site)" is pressed (S21-3 (a));
  - the form is built from the schema at page load: defaults, ranges,
    enums and descriptions as tooltips; conditional fields for extended
    sources, power law and line; CDS sends `n_reads = 1`;
  - the results: S/N per pixel and per resolution element, the line S/N,
    the exposure, the brightest pixel and flag, R and the LSF, the slit
    and aperture fractions, the versions (`meta.keck_etcs_version`,
    `calib_version`, `era`), every warning verbatim, a canvas plot of S/N
    and sky against wavelength, and a JSON download of the inputs and the
    full output;
  - `InputError` is shown as "Invalid input: ...", other exceptions as
    one line (no stack trace);
  - user spectra are left to the Python API, as stated on the page.
- **Plot:** a small canvas plot rather than a JS library from a CDN, which
  would be a third-party request, or matplotlib in Pyodide (+10 MB).

**S21 verification.** The new `scripts/etc_page_check.py` serves the built
HTML, opens `etc.html` in a fresh headless profile, presses Start and
fills the form. Playwright runs in the scratch env with the system Chrome;
its Firefox build was downloaded into the scratchpad, not `~/.cache`.

| | Chrome 149 | Firefox 155 |
|---|---|---|
| Ready after Start (cold) | 6.0 s | 6.5 s |
| Transferred (localhost, uncompressed) | 44.3 MB | 44.3 MB |
| Defaults: `snr_pixel_median`, page against CPython | 4.4727579841692195 against 4.47275798416922 (2e-16), OK | same, OK |
| First compute | 3.80 s | 3.81 s |
| Slit 10" | "Invalid input: slit_width_arcsec: 10 is greater than the maximum of 5.0", no result, OK | same, OK |
| J2 21 AB, `target_snr` 5/resel: `exptime_s` | 237.07418038007444 against 237.07418038007478, OK | same, OK |
| `calib_version` shown | yes | yes |
| Hosts contacted | 127.0.0.1 only | 127.0.0.1 only |

- Screenshots, kept in the scratchpad only, not committed, show the banner,
  the button with its size, the form, the results, the warnings and the
  plot. A left-axis label overlap was fixed.
- No claim is made about offline use.

**S22: pre-publish.**

- **`.readthedocs.yaml`** is unchanged and final: Python 3.12,
  `docs/requirements.txt`, `pip install .` with no extras,
  `fail_on_warning: true`. The S21 wheel and Pyodide steps run in
  `conf.py`, so they need no build jobs; RTD downloads about 40 MB of
  Pyodide per build.
- **`CITATION.cff`** (new): version 0.2.5, BSD-3-Clause, the repository and
  docs URLs, no DOI yet.
- **`docs/citing.md`** ("Citing and versions"): the `meta` version fields,
  the banner, how to cite, and that WMKO's front end will be the official
  tool.
- **`README.md`:**
  - a Read the Docs badge and URL for `keck-mosfire`; the project exists,
    so it is not "pending";
  - release step 7, after the commit: check the published banner and the
    calculator with `etc_page_check.py --url`.
- **`nautilus/README.md`** section 10: step 10, the same check.
- **Checks:**
  - `check_docs_build.py` now covers 19 pages and the calculator's static
    files and config versions;
  - `check_docs.py` checks the `CITATION.cff` version.

**Builds and checks after these changes.**

- `-W` build in `pypeit14b`: 13.2 s, 0 warnings.
- RTD-like build in a fresh venv without PypeIt: 10.8 s, "PypeIt
  importable: False".
- `check_docs_build.py`, `check_docs.py` (213 files, no secret) and
  `pytest` (111 passed): all pass.

**Read the Docs (read-only API).** `keck-mosfire` builds 35063949 and
35063962 succeeded (these predate this prompt's changes); `latest` build
35063843 failed, as accepted in S22-2 (b). With `latest` as the default
version, https://keck-etcs.readthedocs.io/ itself returns 404 until the
merge; the working URL is https://keck-etcs.readthedocs.io/en/keck-mosfire/.

**Next, user:** commit and push `keck-mosfire`. Then I can run the S22
post-push checks:

- the new build's log (no PypeIt, build time, no warnings);
- the published banner, field reference, examples and calculator, with
  `etc_page_check.py --url https://keck-etcs.readthedocs.io/en/keck-mosfire/etc.html`;
- that the push triggered the rebuild.

**Files to commit:**

- new: `CITATION.cff`, `docs/citing.md`, `docs/etc.md`,
  `docs/_static/etc.js`, `docs/_static/etc.css`,
  `docs/pyodide_core.sha256`, `scripts/fetch_pyodide.py`,
  `scripts/pyodide_check.py`, `scripts/etc_page_check.py`;
- modified: `docs/conf.py`, `docs/index.md`, `docs/requirements.txt`,
  `README.md`, `nautilus/README.md`, `scripts/check_docs.py`,
  `scripts/check_docs_build.py`, this prompt doc.

### 2026-10-10 (Prompt #4 / S22: published on Read the Docs; post-push checks pass)

Model: Claude Opus 5.5. The user pushed `keck-mosfire` (`f6e1f00`, "go
time").

**The push triggered a rebuild.** Build **35064669** of `keck-mosfire`
started at 20:08:16Z for commit `f6e1f00` (the webhook works) and finished:
success, **89 s**. The checks below use RTD's public API and log,
read-only.

- **No PypeIt:** the log says "PypeIt importable in the build environment:
  False", and the `pip list` has no pypeit (keck_etcs 0.2.5, furo
  2025.12.19, myst-nb 1.4.0, numpy 2.5.4).
- **No warnings:** no Sphinx `WARNING` (only the kernel's "TCP without
  encryption" log line), "build succeeded", `fail_on_warning: true`.
- **Pyodide self-hosting at build time:** "5 core files + 16 packages, 39.5
  MB ... (21 downloaded, all sha256 verified)"; wheel
  `keck_etcs-0.2.5-py3-none-any.whl`; version line "keck_etcs 0.2.5 /
  calibration mosfire-J-2026.10".
- **Notebook:** executed in 26.8 s on RTD (3 s locally). The total stays
  far inside the 15-minute limit.

**Published pages** (https://keck-etcs.readthedocs.io/en/keck-mosfire/,
fetched with curl):

- the banner "keck_etcs 0.2.5 · calibration mosfire-J-2026.10" is on
  `index`, `etc`, `field_reference`, `examples`, `citing`, `results` and
  `api/etc`;
- the field reference has 67 rows ("Inputs (31 fields)", "Outputs (36
  fields)");
- the examples page prints `snr_pixel_median = 4.47275798416922`,
  identical to the local build and to `pypeit14b`;
- `_static/pyodide/v314.0.7/pyodide.js` and the wheel are served (HTTP
  200).

**Published calculator** (`scripts/etc_page_check.py --url
.../etc.html`):

- **Firefox 155: ALL CHECKS PASS.**
  - Ready 7.7-9.0 s after Start, cold; 37.1 MB transferred, since RTD
    compresses; the button says "about 44 MB" of files.
  - Defaults: `snr_pixel_median` 4.4727579841692195 against CPython
    4.47275798416922; `calib_version` shown.
  - Slit 10": the schema message.
  - The `target_snr` exposure is 237.07418038007444 s against
    237.07418038007478 s.
  - All 25 calculator requests (Pyodide, packages, wheel, `etc_*.json`,
    `etc.js`, `etc.css`) went to `keck-etcs.readthedocs.io`: self-hosted,
    as S21-2 (b) asked.
- **Other hosts:** the page also contacted `media.ethicalads.io` and
  `server.ethicalads.io`. Read the Docs injects these ads into every
  Community (free) site, so they are not the calculator's requests. The
  check script now separates the two:
  - it requires the calculator's files to come from the site;
  - it lists the injected hosts.

  Whether RTD's ads can be turned off is a project-settings question for
  the user; I did not check RTD's current terms.
- **Chrome:** RTD's Cloudflare front end answers *headless* Chrome with a
  bot challenge (HTTP 429, "Just a moment...", seen in the page content).
  A normal user agent did not help either, and I did not try further to get
  around the bot protection; the user-agent change was removed again. So
  Chrome is verified on the identical locally served build (ALL CHECKS
  PASS, with calculator files from the site only). On the published site,
  check it by hand in a normal Chrome window. The script's docstring
  records this.

**S22 Verify:**

- **The published version shows keck_etcs 0.2.5 / `mosfire-J-2026.10`:**
  yes, on `keck-mosfire`.
  - `latest` (`main`) is still the failed build 35063843, as accepted in
    S22-2 (b); it changes after the merge.
  - `stable` needs a tag.
- **A push triggers a rebuild:** yes, build 35064669 for `f6e1f00`.
- **`check_docs.py`:** ALL CHECKS PASS earlier this prompt, with no secret
  in any new file; there have been no changes since except
  `scripts/etc_page_check.py`.

**Public URL:** https://keck-etcs.readthedocs.io/en/keck-mosfire/ (the
calculator is at `etc.html`). The bare https://keck-etcs.readthedocs.io/
still returns 404 until `main` builds (S22-2 (b)).

**Builds:** 35063843 (`latest`, failed), 35063949, 35063962 and 35064669
(`keck-mosfire`, success).

**After the merge (user):**

- `latest` builds from `main`, and the root URL works.
- Point the README badge at `latest`.
- On the first tag, activate `stable`, and mint a Zenodo DOI for
  `CITATION.cff` (S22-3).

**Files changed since the push:** `scripts/etc_page_check.py` (host
classification, Chrome note) and this prompt doc.
