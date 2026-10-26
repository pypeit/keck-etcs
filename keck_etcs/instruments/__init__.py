"""Instrument configurations and data loading (design 5.1)."""


def get(name):
    """Return the :class:`~keck_etcs.instruments.base.Instrument` for a PypeIt spectrograph name."""
    if name == 'keck_mosfire':
        from keck_etcs.instruments.mosfire import MOSFIRE
        return MOSFIRE
    raise KeyError(f'no instrument module for {name!r}')
