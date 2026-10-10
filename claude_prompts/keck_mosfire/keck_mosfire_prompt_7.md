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
- **S21-2. Where the interactive page loads Pyodide from.** Each reader's
  browser downloads Pyodide and its packages when the page is opened.
  - (a) the official Pyodide CDN (jsDelivr), with an exact version pinned
    (recommended: no hosting cost, and browsers cache it). This is a
    third-party request, stated on the page.
  - (b) self-host the Pyodide files we need as static files on RTD: larger
    builds and repository-independent, but no third-party request.
- **S22-3. Citation (optional).** The repository has a BSD-3 `LICENSE` but no
  `CITATION.cff` or DOI.
  - (a) add a `CITATION.cff` now (authors, title, repository, license; no
    DOI), and leave a Zenodo DOI until the first tag after the merge
    (recommended);
  - (b) nothing for now.

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
