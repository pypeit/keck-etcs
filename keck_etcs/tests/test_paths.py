"""keck_etcs.paths: the per-band night layout (design D55, plan S23d)."""
from keck_etcs import paths


def test_legacy_bands_stay_at_the_night_level():
    for band in (None, 'J', 'J2', 'J3'):
        assert paths.night_dir('mosfire', '20220409', band=band) == paths.data_root() / 'mosfire' / '20220409'
        assert paths.s3_prefix('mosfire', '20220409', 'sens', band=band) == 'mosfire/20220409/sens'


def test_other_bands_have_their_own_product_directory_and_share_raw():
    assert paths.night_dir('mosfire', '20121128', band='H') == paths.data_root() / 'mosfire' / '20121128' / 'H'
    assert paths.night_dir('mosfire', '20121128', 'redux', band='K') == paths.data_root() / 'mosfire' / '20121128' / 'K' / 'redux'
    assert paths.night_dir('mosfire', '20121128', 'raw', band='K') == paths.data_root() / 'mosfire' / '20121128' / 'raw'
    assert paths.s3_prefix('mosfire', '20121128', band='H') == 'mosfire/20121128/H'
    assert paths.s3_prefix('mosfire', '20121128', 'raw', band='H') == 'mosfire/20121128/raw'
    assert paths.s3_prefix('mosfire', '20121128', 'harvest', band='Y') == 'mosfire/20121128/Y/harvest'
    assert paths.band_subdir('mosfire', 'K') == 'K' and paths.band_subdir('mosfire', 'J2') == ''
