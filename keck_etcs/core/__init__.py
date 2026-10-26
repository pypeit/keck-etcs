"""Instrument-agnostic ETC core (design 5.1, 5.3).

Pure functions on numpy arrays and floats: no file or network I/O, no
plotting, and no PypeIt import. The instrument modules load data files and
hand arrays to these functions; ``keck_etcs.etc.compute`` combines them.
Wavelengths are vacuum Angstroms (design N5).
"""
