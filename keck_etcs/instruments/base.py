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
    """A period of fixed instrument optics (D6); ``end`` None means open."""
    name: str
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
    moffat_beta: float = 3.5
    gaps: tuple = ()                    # (start, end, warning) periods inside or between eras
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
        return fwhm_pix(slit_width, self.lsf_slope, self.lsf_floor_pix), \
            f'max(w / {self.lsf_slope}, {self.lsf_floor_pix}) (D25)'

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
