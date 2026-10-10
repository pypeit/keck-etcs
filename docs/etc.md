# Interactive calculator

This page runs the same `keck_etcs.etc.compute` as the Python library, but
in your browser: Python itself ([Pyodide](https://pyodide.org)) is loaded
when you press **Start**, from this site (no other server is contacted), and
then every calculation happens on your computer. The first start downloads
the Python runtime, numpy, scipy, astropy and `keck_etcs` (the size is on the
button) and takes some seconds; your browser normally caches it for later
visits.

The inputs below are a subset of the [field reference](field_reference.md),
with the same defaults and ranges; user-supplied spectra need the
[Python API](getting_started.md). Every warning is shown as `compute` returns
it, and the result states the code version, calibration and instrument era
that produced it. W. M. Keck Observatory's own front end will be the
observatory's official tool.

```{raw} html
<div id="keck-etc" data-static="_static/">
  <p id="etc-facts" class="etc-status"></p>
  <div id="etc-start-box">
    <button id="etc-start" disabled>Start the calculator</button>
    <span id="etc-status" class="etc-status"></span>
  </div>
  <div id="etc-main" hidden>
    <form id="etc-form" class="etc-form" onsubmit="return false"></form>
    <button id="etc-compute">Compute</button>
    <button id="etc-reset" class="secondary">Reset to defaults</button>
    <div id="etc-results"></div>
  </div>
  <noscript>This calculator needs JavaScript; the Python API works without it.</noscript>
</div>
<script src="_static/etc.js"></script>
```
