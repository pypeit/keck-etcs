# ETC field reference

Every input and output field of {func}`keck_etcs.etc.compute`, generated from
the JSON schemas (`keck_etcs/schema/etc_input.json` and `etc_output.json`) at
each documentation build by `scripts/gen_field_reference.py`, so this page
cannot drift from the code. The one-page summary for WMKO, with errors,
warnings, versions and the refresh cycle, is the [API note](wmko_api_note.md).

Inputs not given take their default; an unknown field or a value outside its
range raises `keck_etcs.etc.InputError` naming every offending field.
Wavelengths are vacuum Angstroms. Output arrays are per spectral pixel on
`wave_A`; electrons are per spectral pixel in the extraction aperture, summed
over all frames, unless the name says `per_frame`.

```{include} _generated/field_reference_tables.md
```
