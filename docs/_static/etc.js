/* Interactive keck_etcs calculator (plan S21; docs/etc.md).
 *
 * Runs keck_etcs.etc.compute in the reader's browser with Pyodide. Everything is a static file of this
 * site (Q&A S21-2 (b)): Pyodide and its packages (_static/pyodide/v<version>/, fetched and sha256-checked
 * by scripts/fetch_pyodide.py at build time), the keck_etcs wheel of the same source tree
 * (_static/wheels/), the input schema (_static/etc_input.json) and the build facts
 * (_static/etc_config.json). Nothing is loaded until the reader presses "Start" (Q&A S21-3 (a)).
 * The form's defaults, ranges and choices come from the schema, so they cannot drift from the code.
 * For tests, the last result is exposed as window.KECK_ETC = {inputs, output, error}.
 */
(function () {
  'use strict';
  const root = document.getElementById('keck-etc');
  if (!root) return;
  const STATIC = root.dataset.static;             // relative URL of _static/ from this page
  const $ = (sel) => root.querySelector(sel);
  let py = null, schema = null, config = null;

  // ---- form definition: [dotted path, label, kind]; defaults, ranges and options from the schema
  const FIELDS = [
    ['band', 'Band', 'select'],
    ['slit_width_arcsec', 'Slit width (arcsec)', 'number'],
    ['source.type', 'Source', 'select'],
    ['source.mag', 'Magnitude (in the band)', 'number'],
    ['source.mag_system', 'Magnitude system', 'select'],
    ['source.size_arcsec', 'Source diameter (arcsec)', 'number', (v) => v['source.type'] === 'extended'],
    ['spectrum.shape', 'Spectrum', 'select'],
    ['spectrum.alpha', 'Power-law index alpha (f_nu ~ nu^alpha)', 'number', (v) => v['spectrum.shape'] === 'power_law'],
    ['spectrum.line.wave_A', 'Line wavelength (A, vacuum)', 'number', (v) => v['spectrum.shape'] === 'line', 12820],
    ['spectrum.line.flux_cgs', 'Line flux (erg/s/cm^2)', 'number', (v) => v['spectrum.shape'] === 'line', 1e-17],
    ['spectrum.line.fwhm_kms', 'Line FWHM (km/s)', 'number', (v) => v['spectrum.shape'] === 'line'],
    ['spectrum.line.continuum_mag', 'Continuum under the line (mag; blank = none)', 'optional', (v) => v['spectrum.shape'] === 'line'],
    ['seeing_fwhm_arcsec', 'Seeing FWHM (arcsec, at the band)', 'number'],
    ['exptime_s', 'Exposure per frame (s)', 'number'],
    ['n_frames', 'Number of frames', 'integer'],
    ['readout.mode', 'Readout', 'select'],
    ['readout.n_reads', 'Reads (MCDS)', 'select', (v) => v['readout.mode'] === 'MCDS'],
    ['nod', 'Nod pattern', 'select'],
    ['airmass', 'Airmass', 'number'],
    ['pwv_mm', 'PWV (mm)', 'number'],
    ['sky_scale', 'Sky scale', 'number'],
    ['throughput.date', 'Observing date (selects the era; blank = latest)', 'date'],
    ['target_snr', 'Target S/N (blank = use the exposure above)', 'optional'],
    ['snr_reference', 'Target S/N refers to', 'select', (v) => v['target_snr'] !== ''],
  ];
  const SHAPES_SHOWN = ['flat_fnu', 'power_law', 'line'];   // 'user' spectra need arrays: use the Python API

  function prop(path) {
    let node = schema;
    for (const key of path.split('.')) node = node.properties[key];
    return node;
  }

  function buildForm() {
    const form = $('#etc-form');
    form.innerHTML = '';
    for (const [path, label, kind, , fallback] of FIELDS) {
      const p = prop(path);
      const id = 'etc-' + path.replace(/\./g, '-');
      const row = document.createElement('div');
      row.className = 'etc-row';
      row.dataset.path = path;
      let input;
      if (kind === 'select') {
        input = document.createElement('select');
        let opts = p.enum;
        if (path === 'spectrum.shape') opts = opts.filter((o) => SHAPES_SHOWN.includes(o));
        for (const o of opts) {
          const op = document.createElement('option');
          op.value = String(o); op.textContent = String(o);
          input.appendChild(op);
        }
        if (p.default !== undefined) input.value = String(p.default);
      } else {
        input = document.createElement('input');
        input.type = kind === 'date' ? 'date' : (kind === 'text' ? 'text' : 'number');
        if (kind === 'integer') input.step = '1';
        else if (kind !== 'date') input.step = 'any';
        const lo = p.minimum ?? p.exclusiveMinimum, hi = p.maximum;
        if (lo !== undefined && kind !== 'date') input.min = lo;
        if (hi !== undefined && kind !== 'date') input.max = hi;
        const d = p.default !== undefined && p.default !== null ? p.default : fallback;
        if (d !== undefined && d !== null) input.value = d;
        const range = [lo !== undefined ? `${p.exclusiveMinimum !== undefined ? '>' : '>='} ${lo}` : '',
                       hi !== undefined ? `<= ${hi}` : ''].filter(Boolean).join(', ');
        if (range) input.title = range;
      }
      input.id = id;
      const lab = document.createElement('label');
      lab.htmlFor = id;
      lab.textContent = label;
      if (p.description) lab.title = p.description;
      row.append(lab, input);
      form.appendChild(row);
      input.addEventListener('change', updateVisibility);
    }
    updateVisibility();
  }

  function values() {
    const v = {};
    for (const [path] of FIELDS) v[path] = document.getElementById('etc-' + path.replace(/\./g, '-')).value;
    return v;
  }

  function updateVisibility() {
    const v = values();
    for (const [path, , , show] of FIELDS) {
      const row = root.querySelector(`.etc-row[data-path="${path}"]`);
      row.hidden = show ? !show(v) : false;
    }
  }

  function setPath(obj, path, value) {
    const keys = path.split('.');
    let o = obj;
    for (const k of keys.slice(0, -1)) o = (o[k] = o[k] || {});
    o[keys[keys.length - 1]] = value;
  }

  function collectInputs() {
    const v = values(), inputs = {};
    for (const [path, , kind, show] of FIELDS) {
      if (show && !show(v)) continue;
      const raw = v[path];
      if (kind === 'optional' || kind === 'date') {
        if (raw === '') { if (path !== 'spectrum.line.continuum_mag') setPath(inputs, path, null); continue; }
        setPath(inputs, path, kind === 'date' ? raw : Number(raw));
      } else if (kind === 'number') {
        setPath(inputs, path, raw === '' ? NaN : Number(raw));
      } else if (kind === 'integer' || path === 'readout.n_reads') {
        setPath(inputs, path, raw === '' ? NaN : parseInt(raw, 10));
      } else {
        setPath(inputs, path, raw);
      }
    }
    if (inputs.readout && inputs.readout.mode === 'CDS') inputs.readout.n_reads = 1;   // CDS is one read
    return inputs;
  }

  // ---- Pyodide start-up
  async function start() {
    const btn = $('#etc-start'), status = $('#etc-status');
    btn.disabled = true;
    const t0 = performance.now();
    const say = (m) => { status.textContent = `${m} (${((performance.now() - t0) / 1000).toFixed(1)} s)`; };
    try {
      say('Loading Python (Pyodide ' + config.pyodide_version + ')');
      await loadScript(STATIC + config.pyodide_index + 'pyodide.js');
      py = await loadPyodide({indexURL: new URL(STATIC + config.pyodide_index, location.href).href});
      say('Loading numpy, scipy, astropy, pyyaml, jsonschema');
      await py.loadPackage(config.packages);
      say('Installing keck_etcs ' + config.keck_etcs_version);
      const micropip = py.pyimport('micropip');
      await micropip.install(new URL(STATIC + config.wheel, location.href).href);
      py.runPython(`
import json
from keck_etcs import etc as _etc
def _run(inputs_json):
    try:
        return json.dumps({'output': _etc.compute(json.loads(inputs_json))})
    except _etc.InputError as exc:
        return json.dumps({'error': f'Invalid input: {exc}'})
    except Exception as exc:
        return json.dumps({'error': f'{type(exc).__name__}: {exc}'})
`);
      say('Ready');
      $('#etc-start-box').hidden = true;
      $('#etc-main').hidden = false;
      window.KECK_ETC_READY = (performance.now() - t0) / 1000;
    } catch (e) {
      status.textContent = 'Could not start the calculator: ' + e;
      btn.disabled = false;
    }
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = src; s.onload = resolve; s.onerror = () => reject(new Error('cannot load ' + src));
      document.head.appendChild(s);
    });
  }

  // ---- compute and show
  function compute() {
    const inputs = collectInputs();
    const out = $('#etc-results');
    out.innerHTML = '<p>Computing ...</p>';
    setTimeout(() => {       // let the browser paint the message first
      const t0 = performance.now();
      const res = JSON.parse(py.globals.get('_run')(JSON.stringify(inputs)));
      const secs = (performance.now() - t0) / 1000;
      window.KECK_ETC = {inputs: inputs, output: res.output || null, error: res.error || null, seconds: secs};
      if (res.error) {
        out.innerHTML = '';
        const p = document.createElement('p');
        p.className = 'etc-error';
        p.textContent = res.error;
        out.appendChild(p);
        return;
      }
      show(res.output, inputs, secs);
    }, 20);
  }

  function fmt(x, d) { return (x === null || x === undefined) ? '-' : Number(x).toFixed(d); }

  function show(o, inputs, secs) {
    const s = o.summary, sat = o.saturation, m = o.meta;
    const out = $('#etc-results');
    out.innerHTML = '';
    const rows = [
      ['S/N per pixel (band median)', fmt(s.snr_pixel_median, 3)],
      ['S/N per resolution element (band median)', fmt(s.snr_resel_median, 3)],
    ];
    if (s.snr_line !== null && s.snr_line !== undefined) {
      rows.push(['Line S/N', `${fmt(s.snr_line, 3)} over ${fmt(s.line_window_A[0], 1)}-${fmt(s.line_window_A[1], 1)} A`]);
    }
    rows.push(
      ['Exposure', `${fmt(s.exptime_s, 2)} s x ${s.n_frames} frames = ${fmt(s.total_time_s, 1)} s`],
      ['Brightest pixel per frame', `${fmt(sat.peak_adu_per_frame, 0)} ADU at ${fmt(sat.wave_A, 1)} A: ${sat.flag}`],
      ['Resolution', `R ${fmt(o.resolving_power[Math.floor(o.resolving_power.length / 2)], 0)}, LSF ${fmt(o.n_spec_per_resel, 2)} pix`],
      ['Slit and aperture', `slit fraction ${fmt(o.slit_fraction, 3)}, aperture fraction ${fmt(o.aperture_fraction, 3)}, ${o.n_spatial_pix} spatial pix`],
      ['Versions', `keck_etcs ${m.keck_etcs_version}, calibration ${m.calib_version}, era ${m.era}`],
    );
    const tab = document.createElement('table');
    tab.className = 'etc-summary';
    for (const [k, v] of rows) {
      const tr = tab.insertRow();
      tr.insertCell().textContent = k;
      tr.insertCell().textContent = v;
    }
    out.appendChild(tab);
    if (o.warnings.length) {
      const h = document.createElement('p');
      h.textContent = 'Warnings:';
      const ul = document.createElement('ul');
      ul.className = 'etc-warnings';
      for (const w of o.warnings) { const li = document.createElement('li'); li.textContent = w; ul.appendChild(li); }
      out.append(h, ul);
    }
    const canvas = document.createElement('canvas');
    canvas.className = 'etc-plot';
    out.appendChild(canvas);
    plot(canvas, o);
    const blob = new Blob([JSON.stringify({inputs: inputs, output: o}, null, 1)], {type: 'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `keck_etc_${m.calib_version}_${Date.now()}.json`;
    a.textContent = 'Download the inputs and the full output (JSON)';
    const p = document.createElement('p');
    p.append(a, document.createTextNode(` (computed in ${secs.toFixed(2)} s)`));
    out.appendChild(p);
  }

  // ---- a small canvas plot: S/N per pixel (left, linear) and sky electrons (right, log) against wavelength
  function plot(canvas, o) {
    const W = canvas.clientWidth || 700, H = 300, dpr = window.devicePixelRatio || 1;
    canvas.width = W * dpr; canvas.height = H * dpr; canvas.style.height = H + 'px';
    const g = canvas.getContext('2d');
    g.scale(dpr, dpr);
    const css = getComputedStyle(root);
    const fg = css.getPropertyValue('--color-foreground-primary').trim() || '#222';
    const L = 58, R = 56, T = 12, B = 36, w = o.wave_A, snr = o.snr_pixel, sky = o.sky_e;
    const x0 = w[0], x1 = w[w.length - 1];
    const ymax = Math.max(...snr) * 1.05 || 1;
    const lsky = sky.map((v) => Math.log10(Math.max(v, 1e-3)));
    const l0 = Math.floor(Math.min(...lsky)), l1 = Math.ceil(Math.max(...lsky));
    const X = (v) => L + (v - x0) / (x1 - x0) * (W - L - R);
    const Y = (v) => H - B - v / ymax * (H - T - B);
    const YS = (lv) => H - B - (lv - l0) / Math.max(l1 - l0, 1) * (H - T - B);
    g.font = '11px sans-serif'; g.fillStyle = fg; g.strokeStyle = fg; g.lineWidth = 1;
    g.strokeRect(L, T, W - L - R, H - T - B);
    for (let i = 0; i <= 5; i++) {                         // x ticks
      const xv = x0 + (x1 - x0) * i / 5;
      g.fillText(xv.toFixed(0), X(xv) - 16, H - B + 14);
    }
    g.fillText('vacuum wavelength (A)', (W - L - R) / 2 + L - 50, H - 6);
    g.textAlign = 'right';
    for (let i = 0; i <= 4; i++) {                         // left ticks (S/N), right-aligned on the axis
      const yv = ymax * i / 4;
      g.fillText(yv.toFixed(yv < 10 ? 1 : 0), L - 4, Y(yv) + 4);
    }
    g.textAlign = 'left';
    g.save(); g.translate(11, T + 110); g.rotate(-Math.PI / 2); g.fillText('S/N per pixel', 0, 0); g.restore();
    for (let e = l0; e <= l1; e++) g.fillText('1e' + e, W - R + 6, YS(e) + 4);   // right ticks (sky, log)
    g.save(); g.translate(W - 6, T + 40); g.rotate(Math.PI / 2); g.fillText('sky e- per pixel', 0, 0); g.restore();
    const line = (ys, color, width) => {
      g.beginPath(); g.strokeStyle = color; g.lineWidth = width;
      ys.forEach((y, i) => (i ? g.lineTo(X(w[i]), y) : g.moveTo(X(w[i]), y)));
      g.stroke();
    };
    line(lsky.map(YS), 'rgba(70,130,200,0.55)', 0.7);
    line(snr.map(Y), fg, 0.9);
    const med = o.summary.snr_pixel_median;
    g.strokeStyle = 'rgb(230,120,20)'; g.lineWidth = 1.2; g.beginPath(); g.moveTo(L, Y(med)); g.lineTo(W - R, Y(med)); g.stroke();
    g.fillStyle = 'rgb(230,120,20)'; g.fillText(`median ${med.toFixed(2)}`, L + 6, Y(med) - 4);
  }

  // ---- page set-up: read the build facts and the schema, then wait for "Start"
  Promise.all([fetch(STATIC + 'etc_config.json').then((r) => r.json()),
               fetch(STATIC + 'etc_input.json').then((r) => r.json())])
    .then(([c, s]) => {
      config = c; schema = s;
      $('#etc-start').textContent =
        `Start the calculator (downloads about ${Math.round(c.download_mb)} MB once, from this site)`;
      $('#etc-start').disabled = false;
      $('#etc-facts').textContent =
        `keck_etcs ${c.keck_etcs_version}, calibration ${c.calib_version}; ` +
        `Python ${c.pyodide_python} in your browser via Pyodide ${c.pyodide_version}.`;
      buildForm();
      $('#etc-start').addEventListener('click', start);
      $('#etc-compute').addEventListener('click', compute);
      $('#etc-reset').addEventListener('click', buildForm);
    })
    .catch((e) => { $('#etc-status').textContent = 'Could not read the page set-up: ' + e; });
})();
