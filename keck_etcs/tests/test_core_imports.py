"""keck_etcs.core and the schemas import without PypeIt, boto3 or plotting (design 5.1, D38)."""
import subprocess
import sys


def test_core_imports_no_heavy_dependencies():
    code = ('import sys\n'
            'import keck_etcs.core.source, keck_etcs.core.atmosphere, keck_etcs.core.sky\n'
            'import keck_etcs.core.slitloss, keck_etcs.core.lsf, keck_etcs.core.detector, keck_etcs.core.snr\n'
            'import keck_etcs.schema\n'
            "print(','.join(m for m in ('pypeit', 'boto3', 'matplotlib', 'astropy', 'requests') if m in sys.modules))\n")
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ''
