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
    """One spectroscopic band (filter plus grating setting)."""
    name: str
    filter_file: str                    # relative to DATA_DIR
    dispersion_A_per_pix: float
    footprint_A: tuple                  # detector coverage at the long-slit position (N2)
    clean_window_A: tuple = None        # contamination-free part, where one is defined
    notes: str = ''


@dataclass(frozen=True)
class Era:
    """A period of fixed instrument optics (D6); ``end`` None means open.

    ``name`` is the label echoed in outputs (``2017-02..2025-02``); ``tag``
    names its throughput file (``mosfire_thru_<tag>.ecsv``).
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
    throughput_pattern: str = None      # per-era curve, e.g. 'mosfire/throughput/mosfire_thru_{tag}.ecsv' (S10)
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

    def throughput_file(self, era):
        """Path (relative to ``DATA_DIR``) of an era's throughput curve."""
        return self.throughput_pattern.format(tag=era.tag)

    def throughput(self, era):
        """Filter-free system throughput for an era (design 4.5).

        If the era has no curve yet, the nearest era that has one is used
        (the earlier one on a tie), with a warning.

        Returns:
            dict: ``wave_A``, ``thru``, ``era`` (the era actually used),
            ``file``, ``calib_version``, ``pypeit_version``, ``valid_range_A``
            and ``warnings``.

        Raises:
            FileNotFoundError: if no era has a throughput curve.
        """
        def load():
            from astropy.table import Table
            i = self.eras.index(era)
            order = sorted(range(len(self.eras)), key=lambda j: (abs(j - i), j > i))
            have = [j for j in order if (DATA_DIR / self.throughput_file(self.eras[j])).exists()]
            if not have:
                raise FileNotFoundError(f'no throughput curve for any {self.name} era')
            used = self.eras[have[0]]
            rel = self.throughput_file(used)
            t = Table.read(DATA_DIR / rel, format='ascii.ecsv')
            entry = self.index().get('files', {}).get(rel, {})
            warnings = [] if used == era else [f'no throughput curve yet for era {era.name}; using era {used.name}']
            versions = t.meta.get('pypeit_versions') or [entry.get('pypeit_version', 'unknown')]
            return {'wave_A': np.asarray(t['wave'], float), 'thru': np.asarray(t['thru_median'], float),
                    'era': used, 'file': rel, 'warnings': warnings,
                    'calib_version': str(entry.get('calib_version', t.meta.get('calib_version', 'unknown'))),
                    'pypeit_version': ','.join(str(v) for v in versions),
                    'valid_range_A': tuple(t.meta.get('valid_range_A', (float(t['wave'][0]), float(t['wave'][-1]))))}
        return self._load(('throughput', era.name), load)

    SPLICE_WINDOW = (11900.0, 12450.0)
    """Where an era's curve and a donor era's curve are compared to scale the donor (as
    ``keck_etcs.calib.trend.COMMON_WINDOW``)."""

    def throughput_for_window(self, era, lo, hi, margin=0.0):
        """The era's throughput (:meth:`throughput`), completed over ``lo``-``hi`` where it is not measured.

        An era's curve covers only its standards' filters (2025-04..: one J2
        night, 11171-12462 A; 2012-04..2016-09: J only, from 11633 A). Where
        the window extends more than ``margin`` beyond the curve's
        ``valid_range_A``, the uncovered wavelengths are taken from the
        nearest other era whose curve covers them, scaled by the median ratio
        of the two curves over :data:`SPLICE_WINDOW`, with a warning. Without
        such an era the edge value is held (the caller warns).

        Returns:
            dict: as :meth:`throughput`, plus ``spliced`` (list of
            ``(era name, lo, hi, scale)``) and ``covered_A`` (the range now
            covered).
        """
        th = dict(self.throughput(era))
        th['warnings'] = list(th['warnings'])
        th['spliced'] = []
        t_lo, t_hi = th['valid_range_A']
        if lo >= t_lo - margin and hi <= t_hi + margin:
            th['covered_A'] = (t_lo, t_hi)
            return th
        wave, thru = th['wave_A'], th['thru']
        i = self.eras.index(th['era'])
        order = sorted((j for j in range(len(self.eras)) if j != i), key=lambda j: (abs(j - i), j > i))
        s_lo, s_hi = self.SPLICE_WINDOW
        mine = (wave >= s_lo) & (wave <= s_hi)
        for j in order:
            other = self.eras[j]
            if not (DATA_DIR / self.throughput_file(other)).exists():
                continue
            d = self.throughput(other)
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

    def lsf_fwhm_pix(self, slit_width, tol=0.01):
        """``(FWHM_pix, source)``: the median measured FWHM for this slit width, else the D25 rule."""
        rows = [r for r in self.lsf_measurements() if abs(float(r['slit_width']) - slit_width) <= tol]
        if rows:
            fw = float(np.median([r['fwhm_pix'] for r in rows]))
            return fw, f'measured ({len(rows)} row(s) of {self.lsf_file})'
        from keck_etcs.core.lsf import fwhm_pix
        rule = (f'sqrt((w / {self.lsf_slope})^2 + {self.lsf_floor_pix}^2) (D25)' if self.lsf_form == 'quadrature'
                else f'max(w / {self.lsf_slope}, {self.lsf_floor_pix}) (D25)')
        return fwhm_pix(slit_width, self.lsf_slope, self.lsf_floor_pix, form=self.lsf_form), rule

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
