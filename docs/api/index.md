# Python API

The public entry point is {func}`keck_etcs.etc.compute`; everything WMKO needs
is there and in the JSON schemas (`keck_etcs/schema/`). The `core` modules
are the instrument-agnostic physics (pure functions, no I/O), and
`instruments` holds the per-instrument configuration and data access.

```{toctree}
:maxdepth: 1

etc
core
instruments
calib
```
