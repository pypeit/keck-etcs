"""Locations of the out-of-repo data root and the matching S3 bucket keys.

The data root (``$KECK_ETCS_DATA``, default
``~/Projects/PypeIt/keck-etcs-data``) is never committed. It is the local
mirror of the private bucket ``s3://keck-etcs`` on Nautilus S3, with the same
layout (design 4.2)::

    $KECK_ETCS_DATA/
      external/xtcalc/XTcalc_dir/                    # local only, never on S3
      <instrument>/<YYYYMMDD>/raw/                   # the night's raw frames, every band
      <instrument>/<YYYYMMDD>/{redux,sens,harvest}/  # products of the first band group (MOSFIRE J, J2, J3)
      <instrument>/<YYYYMMDD>/<band>/{redux,sens,harvest}/   # products of the other bands (Y, H, K; D55)

    s3://keck-etcs/<instrument>/<YYYYMMDD>/...       # the same keys

Multi-band nights (design D55, plan S23d): the raw frames are shared, and
the products of a (night, band) live under ``<band>/`` with their own
``run_manifest.json`` and ``run.log``, except for the bands of
:data:`LEGACY_BANDS`, whose products stay at the night level as they were
before the other bands existed. :func:`night_dir` and :func:`s3_prefix` are
built from the same parts, so the two layouts cannot drift apart.
"""
import os
from pathlib import Path

DEFAULT_DATA_ROOT = '~/Projects/PypeIt/keck-etcs-data'
"""Default data root, used when ``KECK_ETCS_DATA`` is unset."""

BUCKET = os.environ.get('KECK_ETCS_BUCKET', 'keck-etcs')
"""Name of the S3 bucket; ``KECK_ETCS_BUCKET`` overrides it."""

KINDS = ('raw', 'redux', 'sens', 'harvest')
"""Per-night subdirectories."""

LEGACY_BANDS = {'mosfire': ('J', 'J2', 'J3')}
"""Per instrument, the bands whose products sit at the night level (the layout of the first releases)."""

SHARED_KINDS = ('raw',)
"""Kinds shared by every band of a night."""


def band_subdir(instrument, band):
    """The product subdirectory of a band: ``''`` for None or a legacy band, else the band name."""
    if band is None or str(band) in LEGACY_BANDS.get(str(instrument).lower(), ()):
        return ''
    b = str(band)
    if not b.isalnum():
        raise ValueError(f'band must be alphanumeric, got {band!r}')
    return b


def data_root():
    """Return the data root, from ``KECK_ETCS_DATA`` or the default.

    Returns:
        pathlib.Path: The expanded, absolute data root (it need not exist).
        Symlinks are not resolved.
    """
    root = os.environ.get('KECK_ETCS_DATA') or DEFAULT_DATA_ROOT
    return Path(os.path.abspath(os.path.expanduser(root)))


def _night_parts(instrument, date, kind, band=None):
    instrument = str(instrument).lower()
    date = str(date)
    if len(date) != 8 or not date.isdigit():
        raise ValueError(f'date must be YYYYMMDD, got {date!r}')
    parts = [instrument, date]
    sub = band_subdir(instrument, band)
    if kind is not None:
        if kind not in KINDS:
            raise ValueError(f'kind must be one of {KINDS}, got {kind!r}')
        if sub and kind not in SHARED_KINDS:
            parts.append(sub)
        parts.append(kind)
    elif sub:
        parts.append(sub)
    return parts


def night_dir(instrument, date, kind=None, band=None):
    """Return the local directory of one night's data.

    Args:
        instrument (str): Instrument name, e.g. ``'mosfire'``.
        date (str or int): Night as ``YYYYMMDD``.
        kind (str, optional): One of :data:`KINDS`. If None, return the
            night's product directory itself (where ``run_manifest.json``
            lives).
        band (str, optional): the band of the products (D55). ``raw`` is
            shared by every band; the products of a band outside
            :data:`LEGACY_BANDS` sit under ``<band>/``.

    Returns:
        pathlib.Path: ``data_root()/<instrument>/<date>[/<band>][/<kind>]``.
    """
    return data_root().joinpath(*_night_parts(instrument, date, kind, band))


def s3_prefix(instrument, date, kind=None, band=None):
    """Return the bucket key prefix that matches :func:`night_dir`.

    Args:
        instrument (str): Instrument name, e.g. ``'mosfire'``.
        date (str or int): Night as ``YYYYMMDD``.
        kind (str, optional): One of :data:`KINDS`.
        band (str, optional): as for :func:`night_dir`.

    Returns:
        str: e.g. ``'mosfire/20220409/sens'`` or ``'mosfire/20121128/H/sens'``
        (no bucket, no slashes at either end).
    """
    return '/'.join(_night_parts(instrument, date, kind, band))


def xtcalc_dir():
    """Return the unpacked Keck XTcalc directory under the data root."""
    return data_root() / 'external' / 'xtcalc' / 'XTcalc_dir'
