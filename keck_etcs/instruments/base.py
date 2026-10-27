"""Instrument description and data loading (design 5.1, 5.4).

An :class:`Instrument` holds the configuration of one spectrograph (bands,
eras, LSF parameters, detector and sky files) and loads each data file once,
on first use, handing plain numpy arrays and floats to ``keck_etcs.core``.
It never imports PypeIt.
"""
import datetime
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from keck_etcs.core import detector as core_detector

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
"""``keck_etcs/data``."""


@dataclass(frozen=True)
class Band:
    """One spectroscopic band (filter plus grating setting).

    The fields after ``notes`` were added for the Y/H/K extension (design
    9.5, D58): a band belongs to a **group** (one grating order; the
    filter-free throughput products are per group), and carries the
    wavelengths that the calibration code used to hard-code for J:
    the zero-point nodes of the harvest row (``zp_lo/mid/hi``), the group's
    common window (band medians, the 3-MAD test, the era splice), the PWV
    windows of the harvest's Gemini match, the combine rules (edge trim and
    the A0V blue cut) and the LSF rule. ``lsf`` is a dict ``{'slope',
    'floor_pix', 'form', 'provisional', 'provenance'}`` or None (then the
    instrument's rule applies, with a warning). ``footprint_provisional``
    marks a footprint taken from a nominal coverage rather than measured.
    """
    name: str
    filter_file: str                    # relative to DATA_DIR
    dispersion_A_per_pix: float
    footprint_A: tuple                  # detector coverage at the long-slit position (N2)
    clean_window_A: tuple = None        # contamination-free part, where one is defined
    notes: str = ''
    group: str = None                   # grating order group (Y, J, H, K); defaults to the name
    order: int = None                   # grating order
    zp_nodes_A: tuple = None            # harvest zero-point nodes (lo, mid, hi)
    common_window_A: tuple = None       # the group's common window (combine, trend, splice)
    pwv_window_A: tuple = None          # ((lo, hi), ...) windows of the PWV match; None = whole curve
    pwv_weak: bool = False              # the PWV estimate is weak in this band (flag = pwv_weak)
    edge_trim_frac: float = None        # combine: keep where the filter >= this fraction of its peak
    a0v_min_wave_A: float = None        # combine: keep A0V rows redward of this
    lsf: dict = None                    # LSF rule of the band (see above)
    footprint_provisional: bool = False

    @property
    def group_name(self):
        return self.group or self.name


@dataclass(frozen=True)
class Era:
    """A period of fixed instrument optics (D6); ``end`` None means open.

    ``name`` is the label echoed in outputs (``2017-02..2025-02``); ``tag``
    names its throughput files (``mosfire_thru_<group>_<tag>.ecsv``, one per
    band group; D49).
    """
    name: str
    tag: str
    start: str
    end: str = None
    notes: str = ''


@dataclass
class Instrument:
    """A spectrograph: configuration plus lazily loaded data files."""
    name: str
    area_m2: float
    platescale: float                   # spatial, arcsec/pix
    bands: dict
    eras: tuple
    lsf_slope: float                    # arcsec of slit per pixel of LSF FWHM
    lsf_floor_pix: float
    detector_file: str
    sky_grid_file: str
    lsf_file: str = None
    throughput_pattern: str = None      # per-era, per-group curve: 'mosfire/throughput/mosfire_thru_{group}_{tag}.ecsv' (S10, S23)
    throughput_provisional_pattern: str = None   # a group's placeholder curve when no era has one (S23a)
    moffat_beta: float = 3.5
    gaps: tuple = ()                    # (start, end, warning) periods inside or between eras
    lsf_form: str = 'max'               # D25 rule: 'max' or 'quadrature' (keck_etcs.core.lsf.fwhm_pix)
    monitor: dict = None
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    # ---------------------------------------------------------------- loading
    def _load(self, key, loader):
        if key not in self._cache:
            self._cache[key] = loader()
        return self._cache[key]

    def filter_curve(self, band):
        """``{'wave_A', 'transmission', 'meta'}`` of a band's filter (vacuum A, 0-1)."""
        def load():
            from astropy.table import Table
            t = Table.read(DATA_DIR / self.bands[band].filter_file, format='ascii.ecsv')
            return {'wave_A': np.asarray(t['wave_A'], float), 'transmission': np.asarray(t['transmission'], float),
                    'meta': dict(t.meta)}
        return self._load(('filter', band), load)

    def detector(self):
        """Detector table: ``n_reads``, ``read_noise_e`` arrays and ``meta`` (gain, dark, linearity...)."""
        def load():
            from astropy.table import Table
            t = Table.read(DATA_DIR / self.detector_file, format='ascii.ecsv')
            return {'n_reads': np.asarray(t['n_reads'], int), 'read_noise_e': np.asarray(t['read_noise_e'], float),
                    'meta': dict(t.meta)}
        return self._load('detector', load)

    def sky_grid(self):
        """Sky and transmission grid: ``wave_A`` (vacuum), ``skybg``, ``trans``, ``airmass``, ``pwv_mm``, ``header``."""
        def load():
            from astropy.io import fits
            with fits.open(DATA_DIR / self.sky_grid_file) as h:
                g = h['GRID'].data
                return {'wave_A': h['WAVE'].data.astype(float) * 10.0,
                        'skybg': h['SKYBG'].data.astype(float), 'trans': h['TRANS'].data.astype(float),
                        'airmass': np.asarray(g['airmass'], float), 'pwv_mm': np.asarray(g['pwv_mm'], float),
                        'header': dict(h[0].header)}
        return self._load('sky', load)

    def lsf_measurements(self):
        """Rows of the measured-LSF table as a list of dicts (empty without a table)."""
        def load():
            if self.lsf_file is None or not (DATA_DIR / self.lsf_file).exists():
                return []
            from astropy.table import Table
            t = Table.read(DATA_DIR / self.lsf_file, format='ascii.ecsv')
            return [{c: (r[c].item() if hasattr(r[c], 'item') else r[c]) for c in t.colnames} for r in t]
        return self._load('lsf', load)

    def index(self):
        """``keck_etcs/data/index.yaml`` as a dict (``{'files': {path: entry}}``)."""
        def load():
            import yaml
            return yaml.safe_load((DATA_DIR / 'index.yaml').read_text()) or {}
        return self._load('index', load)

    # ------------------------------------------------------------ band groups
    def group_of(self, band):
        """The group (grating order) of a band name."""
        return self.bands[band].group_name

    def group_bands(self, group):
        """Names of the bands in a group, in definition order."""
        return [b for b, band in self.bands.items() if band.group_name == group]

    def common_window(self, group):
        """The group's common window (A), from its first band that defines one; else :data:`SPLICE_WINDOW`."""
        for b in self.group_bands(group):
            if self.bands[b].common_window_A is not None:
                return tuple(float(x) for x in self.bands[b].common_window_A)
        return self.SPLICE_WINDOW

    def throughput_file(self, era, group='J'):
        """Path (relative to ``DATA_DIR``) of a group's throughput curve for an era.

        The pattern must name the group (``{group}``; D49): a throughput
        product belongs to one grating order, and a pattern without the
        placeholder would let every group read the same file.
        """
        if '{group}' not in self.throughput_pattern:
            raise ValueError(f'{self.name}: throughput_pattern {self.throughput_pattern!r} has no {{group}} '
                             'placeholder; throughput products are per band group (D49)')
        return self.throughput_pattern.format(tag=era.tag, group=group)

    def _throughput_exists(self, era, group):
        rel = self.throughput_file(era, group)
        return rel is not None and (DATA_DIR / rel).exists()

    def throughput_provisional_file(self, group):
        """Path of the group's placeholder curve (None when the instrument has no such pattern)."""
        if self.throughput_provisional_pattern is None:
            return None
        return self.throughput_provisional_pattern.format(group=group)

    def throughput(self, era, group='J'):
        """Filter-free system throughput of a band group for an era (design 4.5).

        If the era has no curve yet, the nearest era that has one is used
        (the earlier one on a tie), with a warning. If no era of the group has
        a curve, the group's provisional curve
        (:attr:`throughput_provisional_pattern`; a placeholder such as the
        XTcalc 2012 efficiency, S23a) is used with a ``PROVISIONAL`` warning.

        Returns:
            dict: ``wave_A``, ``thru``, ``era`` (the era actually used; None
            for a provisional curve), ``file``, ``calib_version``,
            ``pypeit_version``, ``valid_range_A``, ``provisional`` and
            ``warnings``.

        Raises:
            FileNotFoundError: if no era has a throughput curve and there is
            no provisional curve either.
        """
        def load():
            from astropy.table import Table
            i = self.eras.index(era)
            order = sorted(range(len(self.eras)), key=lambda j: (abs(j - i), j > i))
            have = [j for j in order if self._throughput_exists(self.eras[j], group)]
            provisional = False
            if have:
                used = self.eras[have[0]]
                rel = self.throughput_file(used, group)
                warnings = [] if used == era else [f'no throughput curve yet for era {era.name}; using era {used.name}']
            else:
                rel = self.throughput_provisional_file(group)
                if rel is None or not (DATA_DIR / rel).exists():
                    raise FileNotFoundError(f'no throughput curve for any {self.name} era of group {group}')
                used, provisional = None, True
                warnings = [f'PROVISIONAL throughput for the {group} band group ({rel}): no standard has been '
                            f'reduced in this group yet; the curve is a placeholder, not a measurement']
            t = Table.read(DATA_DIR / rel, format='ascii.ecsv')
            entry = self.index().get('files', {}).get(rel, {})
            versions = t.meta.get('pypeit_versions') or [entry.get('pypeit_version', 'unknown')]
            return {'wave_A': np.asarray(t['wave'], float), 'thru': np.asarray(t['thru_median'], float),
                    'era': used, 'file': rel, 'warnings': warnings, 'provisional': provisional,
                    'calib_version': str(entry.get('calib_version', t.meta.get('calib_version', 'unknown'))),
                    'pypeit_version': ','.join(str(v) for v in versions),
                    'valid_range_A': tuple(t.meta.get('valid_range_A', (float(t['wave'][0]), float(t['wave'][-1]))))}
        return self._load(('throughput', group, era.name), load)

    SPLICE_WINDOW = (11900.0, 12450.0)
    """Default splice window (the J group's common window), used for a group whose bands define no
    ``common_window_A``. :meth:`throughput_for_window` compares an era's curve and a donor era's curve
    over the group's :meth:`common_window` to scale the donor."""

    def throughput_for_window(self, era, lo, hi, margin=0.0, group='J'):
        """The era's throughput (:meth:`throughput`), completed over ``lo``-``hi`` where it is not measured.

        An era's curve covers only its standards' filters (2025-04..: one J2
        night, 11171-12462 A; 2012-04..2016-09: J only, from 11633 A). Where
        the window extends more than ``margin`` beyond the curve's
        ``valid_range_A``, the uncovered wavelengths are taken from the
        nearest other era **of the same group** whose curve covers them,
        scaled by the median ratio of the two curves over the group's
        :meth:`common_window`, with a warning. Without such an era the edge
        value is held (the caller warns). A provisional curve is never
        spliced.

        Returns:
            dict: as :meth:`throughput`, plus ``spliced`` (list of
            ``(era name, lo, hi, scale)``) and ``covered_A`` (the range now
            covered).
        """
        th = dict(self.throughput(era, group))
        th['warnings'] = list(th['warnings'])
        th['spliced'] = []
        t_lo, t_hi = th['valid_range_A']
        if th['provisional'] or (lo >= t_lo - margin and hi <= t_hi + margin):
            th['covered_A'] = (t_lo, t_hi)
            return th
        wave, thru = th['wave_A'], th['thru']
        i = self.eras.index(th['era'])
        order = sorted((j for j in range(len(self.eras)) if j != i), key=lambda j: (abs(j - i), j > i))
        s_lo, s_hi = self.common_window(group)
        mine = (wave >= s_lo) & (wave <= s_hi)
        for j in order:
            other = self.eras[j]
            if not self._throughput_exists(other, group):
                continue
            d = self.throughput(other, group)
            if d['era'] != other or not mine.any():
                continue
            o_lo, o_hi = d['valid_range_A']
            need_lo = lo < t_lo - margin and o_lo < t_lo
            need_hi = hi > t_hi + margin and o_hi > t_hi
            if not (need_lo or need_hi):
                continue
            ref = np.interp(wave[mine], d['wave_A'], d['thru'], left=np.nan, right=np.nan)
            ok = np.isfinite(ref) & (ref > 0)
            if not ok.any():
                continue
            scale = float(np.median(thru[mine][ok] / ref[ok]))
            grid = np.arange(min(t_lo, o_lo if need_lo else t_lo), max(t_hi, o_hi if need_hi else t_hi) + 0.5, 1.0)
            own = (grid >= t_lo) & (grid <= t_hi)
            new = np.where(own, np.interp(grid, wave, thru), scale * np.interp(grid, d['wave_A'], d['thru']))
            for side, a, b in (('blue', grid[0], t_lo), ('red', t_hi, grid[-1])):
                if (side == 'blue' and need_lo) or (side == 'red' and need_hi):
                    th['spliced'].append((other.name, float(a), float(b), scale))
                    th['warnings'].append(f'throughput of era {th["era"].name} measured over {t_lo:.0f}-{t_hi:.0f} A; '
                                          f'{a:.0f}-{b:.0f} A from era {other.name} scaled by {scale:.3f} '
                                          f'(median ratio over {s_lo:.0f}-{s_hi:.0f} A)')
            wave, thru = grid, new
            t_lo, t_hi = float(grid[0]), float(grid[-1])
            mine = (wave >= s_lo) & (wave <= s_hi)
            if lo >= t_lo - margin and hi <= t_hi + margin:
                break
        th['wave_A'], th['thru'], th['covered_A'] = wave, thru, (t_lo, t_hi)
        return th

    # ---------------------------------------------------------------- derived
    def band_window(self, band):
        """ETC wavelength window (N2): the filter half-power band intersected with the detector footprint."""
        lo, hi = self.filter_curve(band)['meta']['half_power_A']
        flo, fhi = self.bands[band].footprint_A
        return max(float(lo), flo), min(float(hi), fhi)

    def vega_offset(self, band):
        """(m_AB - m_Vega) of the band, from the filter file's ``meta``."""
        return float(self.filter_curve(band)['meta']['ab_minus_vega'])

    def read_noise(self, mode, n_reads):
        """``(read noise e- per pixel per frame, warnings)`` for a readout mode."""
        n, warnings = core_detector.effective_reads(mode, n_reads)
        d = self.detector()
        return core_detector.read_noise(n, d['n_reads'], d['read_noise_e']), warnings

    def lsf_rule(self, band=None):
        """``(slope, floor_pix, form, provisional, provenance)`` of the LSF rule for a band (D25, D59).

        A band's own ``lsf`` dict wins; otherwise the instrument's rule, marked
        provisional when a band was named (it was fitted on another band).
        """
        b = self.bands.get(band) if band is not None else None
        if b is not None and b.lsf is not None:
            d = b.lsf
            return (float(d['slope']), float(d['floor_pix']), d.get('form', self.lsf_form),
                    bool(d.get('provisional', False)), str(d.get('provenance', '')))
        return self.lsf_slope, self.lsf_floor_pix, self.lsf_form, band is not None, 'instrument rule'

    def lsf_fwhm_pix(self, slit_width, band=None, tol=0.01):
        """``(FWHM_pix, source)``: the median measured FWHM for this slit width, else the D25 rule.

        With ``band``, only measured rows of that band's group count (the
        ``filter`` column of the LSF table; D59), and the band's own rule is
        used when there is no measurement. ``source`` starts with
        ``measured`` or names the rule, with ``(provisional)`` appended when
        the rule was fitted on another band.
        """
        rows = [r for r in self.lsf_measurements() if abs(float(r['slit_width']) - slit_width) <= tol]
        if band is not None:
            group = self.group_of(band)
            rows = [r for r in rows if str(r.get('filter', '')) in self.group_bands(group)
                    or self.bands.get(str(r.get('filter', ''))) is None and str(r.get('filter', '')) == group]
        if rows:
            fw = float(np.median([r['fwhm_pix'] for r in rows]))
            return fw, f'measured ({len(rows)} row(s) of {self.lsf_file})'
        from keck_etcs.core.lsf import fwhm_pix
        slope, floor, form, provisional, _ = self.lsf_rule(band)
        rule = (f'sqrt((w / {slope})^2 + {floor}^2) (D25)' if form == 'quadrature'
                else f'max(w / {slope}, {floor}) (D25)')
        if provisional:
            rule += ' (provisional)'
        return fwhm_pix(slit_width, slope, floor, form=form), rule

    def era_for_date(self, date=None):
        """``(Era, warnings)`` for an ISO date; None gives the latest era.

        A date in a gap between eras takes the era before it, with a warning;
        a date before the first era takes the first.
        """
        if date is None:
            return self.eras[-1], []
        d = datetime.date.fromisoformat(str(date)[:10]).isoformat()
        warnings = [w for (g0, g1, w) in self.gaps if g0 <= d < g1]
        if d < self.eras[0].start:
            return self.eras[0], warnings + [f'throughput.date {d} precedes the first era; using {self.eras[0].name}']
        era = [e for e in self.eras if e.start <= d][-1]
        return era, warnings
