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
