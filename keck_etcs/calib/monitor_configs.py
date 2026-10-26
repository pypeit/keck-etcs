"""Per-instrument calibration-monitor configurations (design 4.9.6).

The MOSFIRE block moved to ``keck_etcs.instruments.mosfire.MONITOR`` in S8;
this module re-exports it so ``keck_etcs.calib.monitor`` and the scripts keep
working unchanged.
"""
from keck_etcs.instruments.mosfire import MONITOR as MOSFIRE, NONLINEAR_ADU as MOSFIRE_NONLINEAR_ADU, \
    PLATESCALE as MOSFIRE_PLATESCALE

CONFIGS = {'keck_mosfire': MOSFIRE}


def get_config(instrument):
    """Return the monitor config for a PypeIt spectrograph name."""
    try:
        return CONFIGS[instrument]
    except KeyError:
        raise KeyError(f'no calibration-monitor config for {instrument!r}') from None
