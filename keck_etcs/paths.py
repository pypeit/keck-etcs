"""Locations of the out-of-repo data root and the matching S3 bucket keys.

The data root (``$KECK_ETCS_DATA``, default
``~/Projects/PypeIt/keck-etcs-data``) is never committed. It is the local
mirror of the private bucket ``s3://keck-etcs`` on Nautilus S3, with the same
layout (design 4.2)::

    $KECK_ETCS_DATA/
      external/xtcalc/XTcalc_dir/                    # local only, never on S3
      <instrument>/<YYYYMMDD>/{raw,redux,sens,harvest}/

    s3://keck-etcs/<instrument>/<YYYYMMDD>/{raw,redux,sens,harvest}/

:func:`night_dir` and :func:`s3_prefix` are built from the same parts, so
the two layouts cannot drift apart.
"""
import os
from pathlib import Path

DEFAULT_DATA_ROOT = '~/Projects/PypeIt/keck-etcs-data'
"""Default data root, used when ``KECK_ETCS_DATA`` is unset."""

BUCKET = os.environ.get('KECK_ETCS_BUCKET', 'keck-etcs')
"""Name of the S3 bucket; ``KECK_ETCS_BUCKET`` overrides it."""

KINDS = ('raw', 'redux', 'sens', 'harvest')
"""Per-night subdirectories."""


def data_root():
    """Return the data root, from ``KECK_ETCS_DATA`` or the default.

    Returns:
        pathlib.Path: The expanded, absolute data root (it need not exist).
        Symlinks are not resolved.
    """
    root = os.environ.get('KECK_ETCS_DATA') or DEFAULT_DATA_ROOT
    return Path(os.path.abspath(os.path.expanduser(root)))


def _night_parts(instrument, date, kind):
    instrument = str(instrument).lower()
    date = str(date)
    if len(date) != 8 or not date.isdigit():
        raise ValueError(f'date must be YYYYMMDD, got {date!r}')
    parts = [instrument, date]
    if kind is not None:
        if kind not in KINDS:
            raise ValueError(f'kind must be one of {KINDS}, got {kind!r}')
        parts.append(kind)
    return parts


def night_dir(instrument, date, kind=None):
    """Return the local directory of one night's data.

    Args:
        instrument (str): Instrument name, e.g. ``'mosfire'``.
        date (str or int): Night as ``YYYYMMDD``.
        kind (str, optional): One of :data:`KINDS`. If None, return the
            night directory itself.

    Returns:
        pathlib.Path: ``data_root()/<instrument>/<date>[/<kind>]``.
    """
    return data_root().joinpath(*_night_parts(instrument, date, kind))


def s3_prefix(instrument, date, kind=None):
    """Return the bucket key prefix that matches :func:`night_dir`.

    Args:
        instrument (str): Instrument name, e.g. ``'mosfire'``.
        date (str or int): Night as ``YYYYMMDD``.
        kind (str, optional): One of :data:`KINDS`.

    Returns:
        str: e.g. ``'mosfire/20220409/sens'`` (no bucket, no slashes at
        either end).
    """
    return '/'.join(_night_parts(instrument, date, kind))


def xtcalc_dir():
    """Return the unpacked Keck XTcalc directory under the data root."""
    return data_root() / 'external' / 'xtcalc' / 'XTcalc_dir'
