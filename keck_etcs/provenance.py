"""Provenance of a keck_etcs run: source revisions and container image.

Inside the Nautilus image the source trees have no ``.git``, so the build
bakes the revisions into ``KECK_ETCS_GIT_SHAS`` (JSON ``{"pypeit": ...,
"keck_etcs": ...}``, design D31/D36) and the job manifests set
``KECK_ETCS_IMAGE`` and ``KECK_ETCS_IMAGE_DIGEST``. Locally the revisions
come from ``git rev-parse``. Nothing here has side effects beyond reading
the environment and running read-only git commands.
"""
import json
import os
import subprocess
from pathlib import Path

UNKNOWN = 'unknown'


def _git_head(path):
    """Full HEAD SHA of the git work tree containing ``path``, or None."""
    try:
        res = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else None


def git_shas():
    """Return ``{'pypeit': sha, 'keck_etcs': sha}``.

    Prefers ``KECK_ETCS_GIT_SHAS``; otherwise asks git about the directories
    the two packages are imported from; otherwise ``'unknown'``.
    """
    env = os.environ.get('KECK_ETCS_GIT_SHAS')
    if env:
        try:
            shas = json.loads(env)
            return {'pypeit': shas.get('pypeit') or UNKNOWN,
                    'keck_etcs': shas.get('keck_etcs') or UNKNOWN}
        except json.JSONDecodeError:
            pass
    out = {}
    import keck_etcs
    out['keck_etcs'] = _git_head(Path(keck_etcs.__file__).resolve().parent) or UNKNOWN
    try:
        import pypeit
        out['pypeit'] = _git_head(Path(pypeit.__file__).resolve().parent) or UNKNOWN
    except ImportError:
        out['pypeit'] = UNKNOWN
    return {'pypeit': out['pypeit'], 'keck_etcs': out['keck_etcs']}


def image_info():
    """Return ``{'image': tag or 'local', 'image_digest': digest or None}``."""
    return {'image': os.environ.get('KECK_ETCS_IMAGE') or 'local',
            'image_digest': os.environ.get('KECK_ETCS_IMAGE_DIGEST') or None}
