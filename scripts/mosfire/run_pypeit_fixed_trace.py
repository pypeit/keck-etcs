#!/usr/bin/env python
"""EXPERIMENT ONLY: run_pypeit with the trace refinement in extraction disabled (S4b investigation).

Usage:
    conda run -n pypeit14b python scripts/mosfire/run_pypeit_fixed_trace.py FILE.pypeit -r REDUX

Wraps ``pypeit.core.spatialprofile.fit_profile`` so that it still fits the
object profile but returns its *input* trace. ``local_skysub_extract`` then
keeps the object-finding trace (``TRACE_SPAT``) through all its
iterations. Everything else is unchanged. This tests whether the trace walk
inside ``local_skysub_extract`` causes the unstable extraction of
m220409_0037. It is not a fix: a fix belongs in PypeIt (CLAUDE.md), and this
script must not be used for production reductions.
"""
import sys

from pypeit.core import skysub, spatialprofile

_orig = spatialprofile.fit_profile


def fit_profile_fixed_trace(image, ivar, waveimg, thismask, spat_img, trace_in, *args, **kwargs):
    profile_model, _trace_new, fwhmfit, med_sn2 = _orig(image, ivar, waveimg, thismask, spat_img,
                                                         trace_in, *args, **kwargs)
    return profile_model, trace_in, fwhmfit, med_sn2


spatialprofile.fit_profile = fit_profile_fixed_trace
# skysub imports the module, but patch any direct reference too
if hasattr(skysub, 'fit_profile'):
    skysub.fit_profile = fit_profile_fixed_trace

if __name__ == '__main__':
    from pypeit.scripts.run_pypeit import RunPypeIt
    sys.exit(RunPypeIt.entry_point() if hasattr(RunPypeIt, 'entry_point')
             else RunPypeIt.main(RunPypeIt.parse_args(sys.argv[1:])))
