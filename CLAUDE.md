# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

This repository generates, and then keeps updated, exposure time calculators
(ETCs) for the Keck spectrographs (e.g. HIRES, ESI, DEIMOS, LRIS, MOSFIRE,
NIRES, NIRSPEC, KCWI). Throughputs, sky, and detector properties are to be
grounded in real, reduced data (PypeIt sensitivity functions and calibrations)
rather than stale design numbers, so the ETCs can be refreshed as new data come
in and shared with the community.

The repository is new. Structure is being added by the numbered tasks in
`claude_prompts/starting_up.md`.

## Project decisions

Settled in the `claude_prompts/starting_up.md` Q&A on 2026-09-29:

- **First targets:** Keck/MOSFIRE in the J band, and Keck/LRIS with the 600/4000
  grism (blue) and the 600/7500 grating (red). Other instruments come later.
- **Throughputs are built from scratch.** Do not rely on the archived PypeIt
  sensfuncs, e.g. `pypeit/data/sensfuncs/keck_deimos_*`. Derive throughput
  from standard stars that we reduce ourselves.
- **Raw data come from KOA** (koa.ipac.caltech.edu). That search has its own
  prompt doc.
- **Sky emission:** in the optical, measure it from our own reduced frames. In
  the NIR, use the Gemini Maunakea sky-background models.
- **Deliverable:** a Python library now. WMKO will eventually host a
  web-based front end. So keep the core free of plotting and I/O side
  effects, with simple serializable inputs and outputs (dicts/JSON) that a web
  service can call.
- **Validation:** against measured S/N from real reductions. The existing Keck
  ETCs are a sanity check only, not a target to match.
- **PypeIt defects:** if a PypeIt value is verified to be wrong, fix it in
  PypeIt itself, as a branch in `/Users/xavier/Projects/PypeIt/PypeIt`. Do not
  work around it here.

## Workflow conventions

- **Git is handled by the user.** I (the user) will perform all git commands —
  staging, committing, branching, pushing, tagging, etc. Do not run `git add`,
  `git commit`, `git push`, `git reset`, `git rebase` or any other
  state-changing git command unless I explicitly ask. Read-only git inspection
  (`git status`, `git diff`, `git log`, `git show`, `git branch`) is fine.
- **Calculations become scripts on disk.** If you do any calculation, generate
  it as a Python script and write it to disk so that I can add it to the
  repository. Do not leave results as ephemeral inline snippets — they should be
  committable and re-runnable.
- **`claude_prompts/` is the source of instruction.** Read the relevant prompt
  doc before acting, and do only the numbered task you were pointed at — not the
  whole file.
- **Log your work.** After finishing a task, append a dated entry under the
  `## Logs` section of the prompt doc you were working from, using the format
  given in that doc's `## Logging` section: `### YYYY-MM-DD (short summary)`
  followed by what was done *and what you learned about the repository*.

## Environment

- Python code runs in the `pypeit14` conda environment. Never the system Python.
  Invoke it as `conda run -n pypeit14 python ...`.

## Related repositories on disk

Consult these for instrument properties rather than guessing:

- `/Users/xavier/Projects/PypeIt/PypeIt` — the PypeIt source.
  - Keck spectrograph definitions: `pypeit/spectrographs/keck_*.py`
    (deimos, esi, hires, kcwi, lris, mosfire, nires, nirspec).
  - ETC ingredients under `pypeit/data/`: `sensfuncs/` (sensitivity
    functions), `extinction/` (extinction curves), `sky_spec/` and `skisim/`
    (sky spectra).
- `/Users/xavier/Projects/PypeIt/PypeIt-development-suite` — the development
  suite, for worked reductions and test data conventions.
