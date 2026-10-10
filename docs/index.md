# keck_etcs: exposure time calculators for the Keck spectrographs

`keck_etcs` predicts signal, noise, S/N and saturation for Keck spectroscopy.
Its throughputs, sky and detector terms come from real, reduced data: standard
stars that we reduce ourselves with [PypeIt](https://github.com/pypeit/PypeIt),
the Gemini Maunakea sky models, and Keck's measured detector values. The
first instrument is **Keck/MOSFIRE, J and J2 long-slit spectroscopy**.

The calculator is a Python library with one JSON-in, JSON-out call,
`keck_etcs.etc.compute`, and a command-line wrapper. W. M. Keck Observatory
will host the observatory's web front end; these pages document the library,
its calibration and its validation.

```{toctree}
:caption: Using the ETC
:maxdepth: 2

getting_started
wmko_api_note
api/index
```

```{toctree}
:caption: Calibration and validation
:maxdepth: 2

results
changes
```

```{toctree}
:caption: Developer
:maxdepth: 1

keck_mosfire_design
developer/nautilus
keck_mosfire_implementation
XTcalc_bug
XTcalc_HOWTO
```
