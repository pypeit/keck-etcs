# Tests and continuous integration

## The test suite

`keck_etcs/tests/` holds the pytest suite (`pytest.ini` at the repository
root sets the paths and markers). The tests fall into three groups.

| Group | Modules | Needs |
|---|---|---|
| ETC: physics, schemas, `compute`, the instrument layer, regression against the frozen example outputs | `test_core_*.py`, `test_etc.py`, `test_instruments.py`, `test_regression.py` | the ETC install only (numpy, scipy, astropy, jsonschema, pyyaml) |
| Calibration pipeline: harvest, combine, trend, monitor, KOA manifests, night-failure sweep, A0V standards | `test_harvest.py`, `test_combine.py`, `test_trend.py`, `test_monitor.py`, `test_koa_manifest.py`, `test_night_failures.py`, `test_standards.py` | the `calib` extra; tests that call PypeIt skip without it (`pytest.importorskip('pypeit')`) |
| Validation (`slow` marker) | `test_validation_j0841.py` | `KECK_ETCS_DATA` with the synced in-pod products of 2022-04-09 |

```
pytest keck_etcs/tests                # unit, schema and regression tests (the default deselects slow)
pytest -m slow --run-slow             # the J0841 validation only (needs KECK_ETCS_DATA)
```

Two tests guard the deployment promise that the ETC needs no PypeIt:
`test_etc.py::test_etc_runs_without_pypeit_or_boto3` and
`test_instruments.py::test_instruments_import_without_pypeit` run `compute`
in a subprocess and assert that `pypeit`, `boto3` and `requests` were never
imported.

**Regression fixtures.** `test_regression.py` compares `compute` on the
three `examples/*.json` inputs with `keck_etcs/tests/data/reference_*.json`
to 1e-6. When the physics or the shipped data change on purpose, regenerate
them and say why:

```
python scripts/regen_regression_fixtures.py --regen --note "why"
```

The note is appended to the "Regression fixtures" section of `CHANGES.md`.

## GitHub Actions

`.github/workflows/ci.yml` runs on every pull request, on pushes to `main`
and on demand (`workflow_dispatch`). It has three jobs, one per way the
package is installed.

| Job | Environment | What it runs |
|---|---|---|
| `etc` | `pip install .[test]` on Python 3.11, 3.12, 3.13 and 3.14; asserts PypeIt is **not** importable | `pytest keck_etcs/tests`; `keck_etc` on every file in `examples/`; `scripts/check_docs.py` (on 3.12) |
| `calib` | Python 3.12; PypeIt installed from GitHub at the commit in `nautilus/pypeit_pin.txt` (the same source the Nautilus image uses), then `pip install .[calib,test]` | `pytest keck_etcs/tests`, so the PypeIt-dependent harvest and A0V tests run instead of skipping |
| `docs` | Python 3.12; `docs/requirements.txt` plus `pip install .`, no PypeIt (the build refuses to run with it) | `sphinx-build -W --keep-going`, as Read the Docs does; `scripts/check_docs_build.py`; `scripts/check_docs.py` against the built examples page; the HTML is kept as a workflow artifact for 7 days |

Notes for maintainers:

- The `docs` job downloads the pinned Pyodide release (about 40 MB) for the
  interactive page and caches it under the hash of
  `docs/pyodide_core.sha256`, so a Pyodide bump invalidates the cache on
  its own.
- The `calib` job follows the PypeIt pin. Moving the pin
  (`nautilus/pypeit_pin.txt`, the image rebuild in `nautilus/README.md`)
  changes what CI tests, which is the intent: the pipeline is tested
  against the PypeIt it runs with.
- The slow validation test is never run in CI: it needs the data root.
- `scripts/check_docs.py` is read-only and fails if the README examples,
  the WMKO note, `CHANGES.md`, the image tables and `index.yaml` disagree,
  so a calibration release that forgets one of them fails CI rather than
  the published site.
- Browser checks of the interactive page (`scripts/etc_page_check.py`,
  `scripts/pyodide_check.py`) need a browser and are run by hand.
