# Keck MOSFIRE Prompts

## Goals

We will use this prompt doc to analyze Keck/MOSFIRE J-band spectra to assess its
sensitivity function and then generate an ETC for WMKO

## Context

You can find raw data for the J2 long slit in `Projects/PypeIt/PypeIt-development-suite/RAW_DATA/keck_mosfire/J2_long`.  There is a PypeIt file for those data in `Projects/PypeIt/PypeIt-development-suite/pypeit_files/keck_mosfire_j2_long.pypeit`

The current ETC is here: `https://www2.keck.hawaii.edu/inst/mosfire/etc.html`

## Prompts

### Design

1. Read through the files in Context.  Then start a conversation with me about assessing the 
sensitivity function of the MOSFIRE instrument over time.  And then constructing a new ETC.
Put your questions to me in the Q&A section.
Use Fable if you can.  Log your work.

2. I have answered your first round of questions.  Read my responses and then continue the conversation.
When we are done, I am going to ask you to generate a design doc in `docs/keck_mosfire_design.md`.
It will include both sensitivity analysis and ETC design.
Use Fable if you can.  Log your work.

3. Proceed to generate a design doc in `docs/keck_mosfire_design.md` after reading my responses
to the second round of questions.
The doc should include both sensitivity analysis and ETC design.
Then proceed to generate an implementation plan.  Call it `docs/keck_mosfire_implementation.md`.
After those are written, I will ask you to generate prompts to guide the implementation in 
the Implementation section below
Use Fable if you can.  Log your work.

4. The Implementation plan looks very good.  Please generate one or more prompt docs to perform it.  Call them `keck_mosfire/keck_mosfire_prompt_1.md`, etc.  
Use Fable if you can.  Log your work.


## Q&A

### Design

*2026-09-29, from Prompt #1. Each question ends with my recommended default,
so "agree" is a complete answer.*

**Framing.** We have one night, 2022-04-09 (Hennawi, Nanni, Schindler, Wang,
Yang): J0841+3814 in 4 x 150 s ABBA (+/-2") on LONGSLIT-46x1 at airmass 1.07,
LDS749B in 2 x 120 s AB (+/-6.5") on LONGSLIT-46x5 at airmass 1.58, and
lamp-on/off dome flats. Everything on sky is MCDS-16 (`SAMPMODE=3`,
`NUMREADS=16`), gain 2.15 e-/ADU. The headers carry no read noise, no seeing or
guider FWHM, and no weather or PWV cards, so those must be measured from the
data or fitted. LDS749B resolves in PypeIt to CALSPEC `lds749b_stisnic_008`
(STIS+NICMOS, observed, 40 A sampling in J); it is a DBQ4 helium white dwarf,
J about 15.0 Vega, so it is a legitimate NIR flux standard but a faint one (GD71
is 1.2 mag brighter, Feige 110 2.4 mag). HIP 17971, the A0V used in the dev
suite H and K setups, is in no PypeIt archive; A0V stars need the Vega-model plus
2MASS route. PypeIt's MOSFIRE sensfunc uses the `IR` algorithm with
`TellPCA_3000_26000_R10000.fits` (6 MB, S3), and **that grid is not on this
machine** (`~/.cache/pypeit` is empty); it will download on first use. PypeIt
also hard-codes read noise 5.8 e- regardless of `NUMREADS`, while Keck's
detector page gives CDS 21, MCDS-4 10.8, -8 7.7, -16 5.8, -32 4.2, -64 3.5,
-128 3.0 e-, dark < 0.008 e-/s, and linearity 1% to 26k ADU, 5% to 37k, saturation
43k ADU. The existing Keck ETC (XTcalc, IDL, G. Rudie v2.3, July 2012) uses
throughput and sky measured during May 2012 commissioning: J end-to-end peak
0.32, median 0.28 across 1.12-1.37 um after x0.89^2 for the two Keck mirrors;
read noise 15/sqrt(N_reads) (3.75 e- at 16 reads, vs 5.8 measured); dark
0.005; no slit losses ("object assumed <= slit width"); Gemini/Lord ATRAN
transmission at airmass {1, 1.5, 2} and PWV {1, 1.6, 3, 5} mm; S/N per spectral
pixel; and for N_exp > 1 a two-point dither that doubles sky, dark and read
variance. It has no J2/J3/H1/H2. Its tarball also ships the Gemini Maunakea
sky-background models `mk_skybg_zm_*_ph` as IDL save files (readable with
`scipy.io.readsav`), which matters because gemini.edu returns 403 to fetches.
Instrument eras from the MOSFIRE news page: commissioning 2012; offline
2016-09 to 2017-02 for a dislodged collimator element (the one clear optical
era break); guider detector swap 2020-02 (not the science array); CSU
inoperable 2025-02 to 2025-04, fixed 1" long slit only; and since 2026-08-26
the instrument is warm for cold-head servicing. The H2RG has never been
replaced.

### (a) Assessing the MOSFIRE sensitivity function over time

1. **Which standards to pull from KOA.** Two classes: spectrophotometric white
   dwarfs (GD71, GD153, G191-B2B, Feige 110, LDS749B, plus any other CALSPEC
   star) and A0V telluric stars (HIP numbers; almost every MOSFIRE program
   takes one). *Default:* use the white dwarfs as the absolute anchors and the
   A0V stars as the dense time series, fluxed with PypeIt's Vega model scaled to
   the 2MASS J magnitude (0.02-0.03 mag floor). Cross-tie the two on nights that
   have both. Search KOA on `MASKNAME LIKE 'LONGSLIT%'` (and `long2pos`) with
   J, J2 or J3 filters and match `TARGNAME`/coordinates to those lists.
>A. Agreed
2. **Is LDS749B worth keeping as an anchor?** It is faint and the CALSPEC NIR
   piece is NICMOS at 23-310 A sampling, but a He-atmosphere DBQ has no Paschen
   lines, so it is a clean continuum. *Default:* use it for the 2022-04-09
   sensfunc (it exercises the pipeline; I expect S/N of order 50-100 per pixel
   between OH lines in the 5" slit) but weight the long-term zero point toward
   the DA stars, letting PypeIt mask Pa-beta/Pa-gamma.
>A. Agreed
3. **Wide slit vs narrow slit.** LDS749B is on a 5" slit, the science on 1".
   *Default:* derive throughput only from standards on slits >= 3" (46x5,
   46x3, `long2pos_specphot`), where slit loss is negligible; use narrow-slit
   standards separately to calibrate the ETC's slit-loss model against the
   spatial FWHM PypeIt fits. Do you know whether Keck's standard-star protocol
   for MOSFIRE ever used the 5" slit routinely, or is 2022-04-09 unusual?
>A. Agreed, and I'm not sure.  I will ask Josh Walawender when he is free
4. **What to track and against what.** *Default:* per standard, the
   telluric-corrected zero point (AB mag giving 1 e-/s/A) at 1.20, 1.25 and
   1.30 um and the band-median throughput over the J2 clean region
   (1.117-1.260 um in PypeIt's `tweak_standard`), each with airmass and the
   fitted PWV. Plot against date with the eras above marked (2012-2016.7,
   2017.1-2025.1, 2025.3+). Keck I segments are recoated a few at a time, so I
   would not look for a discrete recoat step. J, J2 and J3 share grating and
   detector, so the three can be combined once the filter curves are divided
   out. Agree, or do you want the metric defined per filter?
>A. Agreed
5. **Tellurics and PWV.** There is no PWV in the headers. *Default:* let the
   `IR` sensfunc fit airmass and water per standard and record them; define the
   zero point at airmass 1 with the telluric model divided out; in the ETC,
   apply the Gemini transmission grid at the user's airmass/PWV. Ignore NIR
   continuum extinction (PypeIt's `mkoextinct.dat` stops at 1.2 um; the J
   continuum term is a few hundredths of a magnitude per airmass and mostly
   water, which the telluric model already carries).
>A. Agreed
6. **Sensfunc fitting details.** PypeIt sets `polyorder = 13` for MOSFIRE and
   trims J2 to 1.117-1.260 um. Thirteen is high for a 1400 A window and the
   J2 blue edge is the filter cut-on, not the detector edge. *Default:* fit a
   lower order (5-7) for the J2 zero point, and check the red trim against the
   fluxed standard. Also: do you trust 1.260 um as the clean red edge, or should
   the ETC cover the full J2 footprint on the detector?
>A. Agreed
7. **More data from the same program.** The J0841+3814 frames come from the
   Hennawi/Yang/Wang high-z quasar program, which ran many J-band longslit
   nights. *Default:* when the KOA prompt doc starts, prioritize those nights
   (public after 18 months): same setup, likely HIP A0V standards, and the
   quasar spectra give many independent S/N validation points.
>A. Agreed

### (b) Building the new ETC

8. **Scope.** *Default:* the core is band-agnostic; ship J and J2 first from
   the same grating with separate filter curves, then Y/H/K as their standards
   are reduced (dev suite has raw-file names for GD71 in Y and HIP 17971 in H
   and K, but no raw data on disk; the `Y_long` sensfunc test exists).
>A. Agreed
9. **Inputs and outputs (JSON).** *Default inputs:* band; slit width; source
   type (point with seeing FWHM and a Moffat profile, or extended with size and
   surface brightness); magnitude (AB default, Vega accepted; XTcalc's J offset
   is +0.91, ours should come from our filter curve); spectral shape (flat
   f_nu, power law, user spectrum, or an emission line with flux, wavelength
   and width); exposure time per frame and number of frames; readout mode
   (`MCDS` with N reads); nod pattern (ABBA or stare); airmass; PWV; spatial
   extraction aperture. *Default outputs:* wavelength arrays of S/N per pixel
   and per resolution element, source, sky, dark and read-noise electrons,
   band-median S/N, and saturation flags. Anything to add or cut?
>A. Agreed
10. **Read noise, dark, saturation.** *Default:* interpolate the measured Keck
    table in log N_reads (not 15/sqrt(N)); dark 0.008 e-/s; flag 1% (26k ADU),
    5% (37k) and saturation (43k) per frame including sky lines. The header
    `SATURATE = 33000` disagrees with the web page's 43k; I would use the web
    page and note the discrepancy. Do you also want UTR supported?
>A. Agreed; I don't know what UTR is.
11. **Sky model.** The project decision is the Gemini `mk_skybg_zm` grid
    (ph/s/arcsec^2/nm/m^2; airmass 1.0/1.5/2.0, PWV 1.0/1.6/3.0/5.0 mm, 0.02 nm
    steps, 0.9-5.6 um), which we now have locally from the XTcalc tarball.
    *Default:* use it, but validate its OH-line and inter-line levels against
    the sky PypeIt models in the J0841+3814 frames, fluxed with our sensfunc,
    and expose a "sky scale" factor since OH varies by 2x through a night.
    Interpolate in airmass and PWV within the grid and clip outside it.
>A. Agreed
12. **Nod-subtraction noise and extraction.** *Default:* for ABBA, variance =
    S t + 2 (B t + n_pix D t + n_pix RN^2) per frame, following XTcalc; point
    sources use an extraction aperture of 1.5 x FWHM in the spatial direction
    with the enclosed fraction from the Moffat profile times the slit
    transmission. PypeIt's optimal extraction is closer to an effective aperture
    of about 1.2 x FWHM; I would calibrate that factor in validation rather
    than model it. Agree?
>A. Agreed
13. **S/N convention.** XTcalc reports S/N per spectral pixel (median over the
    band). *Default:* report both per pixel and per resolution element
    (R = 3310 x 0.7"/slit width in J from XTcalc; we should measure R from the
    OH lines in our frames instead), with the per-pixel median as the headline
    for comparability with XTcalc. Or would you rather headline per resolution
    element?
>A. Agreed
14. **Validation target.** *Default:* reduce the four J0841 frames, flux them
    with the LDS749B sensfunc, and compare PypeIt's measured S/N per pixel
    (`med_s2n` and the ivar array) with the ETC run on the fluxed spectrum at
    the frame's airmass, slit and fitted FWHM. The fluxed spectrum is the input
    and the noise is the output, so the test is not circular. Target agreement
    within 20 percent over the band, tighter between OH lines.
>A. Agreed
15. **PypeIt fixes to file.** (i) `ronoise` should follow `NUMREADS` and
    `SAMPMODE` from the header via the Keck table instead of a fixed 5.8;
    (ii) `darkcurr` is fine; (iii) `saturation = 1e9` stays a reduction hack, the
    real limits live in `keck_etcs`. *Default:* I draft (i) as a small branch
    in the PypeIt checkout for you to review when the RN table is confirmed.
    Agree?
>A. Agreed

*2026-09-29, from Prompt #2. Round 1 is all agreed; one open item and one
term to explain, then the questions I still need answered before drafting
`docs/keck_mosfire_design.md`.*

**Settled so far.**
- Standards: CALSPEC white dwarfs anchor the absolute scale; A0V (HIP) stars,
  fluxed by Vega model x 2MASS J, give the dense time series. LDS749B is used
  for 2022-04-09 but down-weighted long term.
- Throughput comes only from slits >= 3"; narrow-slit standards calibrate the
  slit-loss model. Metric: telluric-corrected zero point at 1.20/1.25/1.30 um
  and the J2 band median, tracked by date against the 2012-2016.7,
  2017.1-2025.1 and 2025.3+ eras. J, J2 and J3 are combined after dividing out
  filter curves.
- Tellurics and PWV are fitted per standard by PypeIt's `IR` sensfunc (lower
  `polyorder`, 5-7); the zero point is defined at airmass 1; NIR continuum
  extinction is ignored; the ETC applies the Gemini transmission grid.
- ETC: band-agnostic core, J and J2 first; JSON in and out with the inputs and
  outputs of Q9; measured RN table interpolated in log N_reads; dark 0.008;
  linearity flags at 26k/37k/43k ADU; Gemini `mk_skybg` sky with a scale
  factor; ABBA doubles background variance; Moffat slit loss with a 1.5 x FWHM
  aperture calibrated in validation; S/N per pixel headline, per resolution
  element also returned; validation against J0841+3814 to 20 percent.
- PypeIt fix to draft: `ronoise` from `NUMREADS`/`SAMPMODE`.
- **Open item (Q3), waiting on Josh Walawender (WMKO):** was the 5" long slit
  ever routine for MOSFIRE standards, or is 2022-04-09 unusual? This decides
  how many wide-slit standards KOA will yield.

16. **UTR, and whether the ETC should support it.** An H2RG is read
    non-destructively, so the controller can sample the accumulating charge
    many times during one exposure. *MCDS* (also called Fowler-N) takes N reads
    at the start and N at the end of the integration and differences the two
    averages; read noise falls roughly as 1/sqrt(N) until 1/f noise flattens
    it, which is why Keck's table goes 21 -> 5.8 -> 3.0 e- from CDS to MCDS-128.
    *UTR* (up-the-ramp) instead spaces the N reads evenly through the exposure
    and fits a slope to counts versus time; it gives similar read-noise
    reduction, plus cosmic-ray rejection and a wider dynamic range because
    saturation can be detected mid-ramp, at the cost of a more complex noise
    model (the slope variance depends on N, the read cadence and the flux).
    MOSFIRE's readout system offers both: our headers document
    `SAMPMODE 1:Single, 2:CDS, 3:MCDS, 4:UTR`, and the detector paper (Kulas et
    al. 2012) says MCDS and UTR are both available to observers and recommends
    MCDS for spectroscopy. Keck's detector page tabulates only CDS and MCDS,
    every on-sky frame we have is MCDS-16, and PypeIt does not read `SAMPMODE`
    or `NUMREADS` at all (it treats each frame as a single image with RN 5.8).
    *Default:* v1 supports CDS and MCDS-N only, with `readout_mode` and
    `n_reads` in the JSON schema so UTR can be added later; the KOA census in
    the next prompt doc records the `SAMPMODE` distribution, and we add UTR
    only if it is more than a few percent of science frames. Agree?
>A. Agreed

### (c) What I still need for the design doc

17. **Package layout.** *Default:* `keck_etcs/core/` holds the
    instrument-agnostic physics as small pure functions and dataclasses
    (`source.py`, `atmosphere.py`, `sky.py`, `slitloss.py`, `lsf.py`,
    `detector.py`, `snr.py`); `keck_etcs/instruments/mosfire.py` holds the
    instrument config (bands, dispersion, R, filter curves, RN table, linearity,
    eras) and later `lris.py`; `keck_etcs/etc.py` exposes one entry point,
    `compute(inputs: dict) -> dict`, plus a JSON-schema file for WMKO;
    `keck_etcs/calib/` holds the sensitivity-analysis code that turns PypeIt
    `.sens` files into throughput products and trend tables; `keck_etcs/data/`
    holds the shipped calibration files; `scripts/mosfire/` holds the
    per-standard reduction drivers and one-off analyses; `bin/keck_etc` is a
    thin CLI reading and writing JSON. No plotting or I/O in `core`.
>A. Use the default
18. **Data file formats and provenance.** *Default:* ECSV (astropy) for every
    1-D table under about 1 MB, because it is human-readable and diffs in git:
    filter curves, RN table, per-standard zero points, the combined throughput
    curve per band and era. FITS for the sky and transmission grids (a 2-D
    image per grid with a shared wavelength extension). Every file carries a
    `meta` block with `instrument`, `band`, `era`, `standards` (names, dates,
    KOA IDs), `pypeit_version`, `keck_etcs_version`, `created`, `script`, and
    a `source` string for third-party inputs (Gemini, Keck detector page,
    CALSPEC version). A `keck_etcs/data/index.yaml` lists the products and
    their versions.
>A. Use the default
19. **Combining many standards into the ETC's "current" throughput.**
    *Default:* per era, the pixel-wise median of the individual
    telluric-corrected throughput curves (each resampled to a common 1 A grid),
    with the MAD as a scatter estimate stored alongside; the ETC default is the
    latest era's median; an optional `date` input selects the era instead; a
    `throughput_scale` input lets a user or WMKO apply a global factor. Nights
    that deviate by more than 3 MAD in band median are flagged and excluded,
    not clipped pixel by pixel. Per-standard curves stay in the repo as an
    ECSV archive so the trend can be re-plotted without re-reducing.
>A. Use the default
20. **Where the Gemini sky grid lives.** The 24 native IDL files are 45 MB. Cut
    to MOSFIRE's 0.95-2.45 um they are 7.2 MB as float32 at the native
    0.02 nm, 1.4 MB at 0.1 nm (`scripts/size_gemini_sky_subset.py`). MOSFIRE's
    narrowest LSF is about 0.36 nm FWHM, so 0.05 nm still oversamples it 7x.
    *Default:* flux-conserving rebin of all 24 grids to 0.05 nm over
    0.95-2.45 um, stored as one FITS file of about 3 MB under
    `keck_etcs/data/sky/`, committed to git, with the conversion script and
    provenance in the header. No git-lfs and no download-on-first-use; the
    original tarball stays outside the repo.
>A. Use the default
21. **Reduction workflow and storage outside the repo.** *Default:* a data root
    given by `KECK_ETCS_DATA` (suggest
    `/Users/xavier/Projects/PypeIt/keck-etcs-data`), laid out as
    `mosfire/<YYYYMMDD>/raw/`, `redux/` and `sens/`; nothing there is in git.
    A driver script per instrument (`scripts/mosfire/reduce_standard.py`)
    runs `pypeit_setup`, `run_pypeit` and `pypeit_sensfunc` with a
    repo-owned `.sens` parameter file, then a harvest script reads every
    `sens_*.fits` into the per-standard ECSV table in `keck_etcs/data/`. Only
    the harvested tables and the combined products are committed. Is that root
    path and env-var name fine?
>A. Use the default
22. **Resolution and LSF model.** *Default:* Gaussian LSF whose FWHM in pixels
    is the slit width projected onto the detector (slit / 0.24"/pix in
    XTcalc's convention, consistent with the 1.48 anamorphic factor in the
    header) with a floor of about 2.2 pix for the optical blur, and
    R = lambda / (FWHM x dispersion); seeing narrower than the slit does not
    narrow the LSF in v1. We measure the floor and the slope from OH-line
    widths in the J0841 frames (PypeIt's wavecal `fwhm`) and store them per
    band in the instrument config, replacing XTcalc's R-theta products.
>A. Use the default
23. **Slit-loss details.** *Default:* Moffat with beta = 3.5, FWHM given by the
    user at the observing band (no wavelength scaling by default; an optional
    `seeing_wave` input applies lambda^-0.2 if they quote an optical value);
    slit transmission is the 1-D integral of the 2-D profile across the slit,
    the spatial aperture fraction is the integral along the slit over
    1.5 x FWHM, no centering error, and extended sources use a top-hat of the
    given size convolved with the same Moffat.
>A. Use the default
24. **Testing strategy.** *Default:* pytest unit tests in `keck_etcs/tests/`
    with analytic cases (Poisson-only limit, zero-width source has unit slit
    transmission, RN scaling with N_reads, ABBA factor of 2); a JSON regression
    fixture that freezes `compute()` output for a reference J and J2 input and
    fails on any change beyond 1e-6 unless the fixture is regenerated on
    purpose; the XTcalc comparison as a script in `scripts/` that re-implements
    XTcalc's formula on its own data files and tabulates the ratio to ours,
    documented in the design doc but not a CI test; and the J0841 validation as
    a `slow`-marked test that needs `KECK_ETCS_DATA`.
>A. Use the default
25. **Versioning and changelog for WMKO.** *Default:* semantic versions for the
    code, date-based tags for calibration products (`mosfire-J-2026.10`), both
    echoed in every JSON output together with `pypeit_version`; a `CHANGES.md`
    with a section per calibration release stating which standards were added
    and how the band-median throughput moved; a calibration release is a
    single commit touching only `keck_etcs/data/` and `CHANGES.md`, so WMKO can
    diff it.
>A. Use the default
26. **What "done" means for the MOSFIRE J milestone.** *Default:* (i) a
    throughput trend table and plot from LDS749B plus at least 10 KOA
    standards spanning at least two eras; (ii) `compute()` working for J and
    J2 with the JSON schema and regression tests passing; (iii) J0841+3814
    S/N reproduced within 20 percent; (iv) `docs/keck_mosfire_design.md` and a
    README usage example; (v) the PypeIt `ronoise` branch filed; (vi) a
    one-page API note for WMKO. Y/H/K, UTR and multi-slit masks are out of
    scope for the milestone.
>A. Use the default

**Where this leaves the design doc.** With answers to 16-26 I can draft
`docs/keck_mosfire_design.md` in full. Nothing hard blocks it: Josh's answer
on the 5" slit and the KOA `SAMPMODE` census only change numbers in the
sensitivity section, and I would mark both as TBD in the draft.

## Logs

### 2026-09-29 (Prompt #1: context survey and Q&A for MOSFIRE J)

Read `CLAUDE.md`, `starting_up.md` (its Q&A and Logs) and this doc, then the
four context sources, and wrote the Q&A above. No git commands were run other
than read-only ones. All calculations are scripts in `scripts/`:

- `scripts/inspect_mosfire_j2_headers.py`: tabulates ETC-relevant header cards
  for the 16 raw frames and dumps a science and a standard header.
- `scripts/check_mosfire_standards.py`: runs PypeIt's own standard lookup
  (`pypeit.core.standard.get_standard_spectrum`) for LDS749B, GD71, HIP 17971,
  Feige 110, G191-B2B and GD153 and reports archive, file, wavelength range and
  J / J2 sampling and flux.
- `scripts/inspect_xtcalc_files.py`: reads the XTcalc tarball (downloaded to the
  scratchpad, not the repo): filter and throughput tables, the
  `MosfireSpecEff/*eff.sm.dat` and `MosfireSkySpec/*sky_cal_pA.sav` files the
  IDL code actually uses, and the Gemini `mk_skybg`/`mktrans` IDL save files.

**Raw data (RAW_DATA/keck_mosfire/J2_long, 16 files, 2048x2048 float32 plus
four mask-table extensions).** Flats 0017-0026: 10 s requested (TRUITIME 8.73
s), CDS (`SAMPMODE=2`), lamp on 0017-0021 and off 0022-0026. Science
0036-0039: J0841+3814_OFF, 150 s each, MCDS-16 (`READDONE=32`), Mask Nod
A/B/A/B with `YOFFSET` +/-2", airmass 1.072-1.080, slit PA 71.5, `TARGWAVE`
1.181 um. Standard 0218-0219: LDS749B, 120 s each (TRUITIME 119.29 s),
MCDS-16, nod +/-6.5", LONGSLIT-46x5, airmass 1.578 and 1.559 at elevation 39
deg, taken 9 hours after the science. `SYSGAIN=2.15`, `PSCALE=0.1799`,
`BUNIT='ADU per coadd'`, `SATURATE=33000` "from config file". Absent: any
read-noise card, seeing or guider FWHM, and weather (`WX*`) cards; the only
guider card is `GUIDWAVE`. Slit width exists only inside `MASKNAME`, which is
how PypeIt's compound `slitwid` meta gets it. Observers were Hennawi, Nanni,
Schindler, Wang and Yang.

**Keck ETC (XTcalc).** The web page is a landing page for an IDL VM program;
the tarball (46 MB) and 7-page PDF (v2.3, 2012-07-02) hold the substance:
inputs band/slit/theta/N_exp/N_reads/magnitude or line flux/exptime or S/N/
airmass and PWV; constants A = 75 m^2, 0.18"/pix, RN 15 e- CDS / sqrt(N_reads),
dark 0.005, dispersion J 1.303 A/pix, R-theta J 2317"; throughput from May
2012 on-sky standards (CCS) times Keck mirror reflectance^2 (0.89 in J): J
end-to-end peak 0.319, median 0.276 over 1.117-1.373 um; sky = MOSFIRE-measured
2012 spectra per band in erg/s/cm^2/A per spatial pixel through 0.7", scaled by
slit width x theta; Gemini transmission only for the atmosphere; no slit
losses; S/N per spectral pixel (magnitude mode) or per line FWHM; two-point
dither doubles background variance. My first `tar tf | head` truncated the
listing and made me think the measured sky/throughput directories were
missing; a `find` showed they are present. Keck's throughput page confirms the
May 2012 provenance and the detector page gives the RN-vs-reads table and the
linearity limits quoted in the Q&A. The filters page gives J 1.253/0.200 um
and J2 1.181/0.129 um (center/FWHM). The Gemini site itself returned HTTP 403.

**PypeIt MOSFIRE support.** `keck_mosfire.py`: gain 2.15, `ronoise` 5.8 fixed
("for 16 reads"), `darkcurr` 28.8 e-/pix/hr, `saturation` 1e9 hack,
`nonlinear` 1.0; sensfunc `IR`, `polyorder` 13, `extrap_blu/red` 0,
`telgridfile = TellPCA_3000_26000_R10000.fits`; `tweak_standard` zeroes J2
outside 11170-12600 A and Y outside 9520-11256 A; standards are typed by
`exptime < 20 s`, so the 120 s LDS749B frames had to be typed by hand in the
pypeit file. The telluric grids live in `pypeit/data/telluric/atm_grids/`
(empty by design) and are fetched from `s3_cloud` into the astropy cache at
`~/.cache/pypeit`; `cache.search_cache('TellPCA')` returns `[]`, so the first
`pypeit_sensfunc` run will download 6 MB. Standard lookup moved to
`pypeit.core.standard` (`get_standard_spectrum`, `CalSpecFluxStandard` etc.,
attributes `.wave`, `.flux`, `.file`, `.meta`); GD71, Feige 110 and GD153
resolve to the `xshooter` archive first, LDS749B and G191-B2B to `calspec`.
In `calspec_info.txt` the `Dwave_range` columns are wavelength steps, not
uncertainties. Dev suite: nine `keck_mosfire_*.pypeit` files (Y/J/J2/H/K,
long, multi, long2pos); standards GD71 (Y, 46x1), HIP 17971 (K 46x1.5; H
3x0.7), LDS749B (J2 46x5); the only sens file is `keck_mosfire_Y_long.sens`
(`algorithm = IR`), used by the `Y_long` sensfunc test; no MOSFIRE tellfit,
fluxing or coadd1d files.

**Instrument history** (MOSFIRE news page): collimator element dislodged,
offline 2016-09 to 2017-02; guider detector replaced 2020-02; CSU errors
2023-09; CSU inoperable 2025-02 to 2025-04 (1" long slit only); warming for
cold-head servicing since 2026-08-26. The 2024-03 SSC notes add K1 pier-repair
downtimes Mar-Apr and Aug-Sep 2025 but nothing MOSFIRE-specific. Web search
found no science-detector or electronics replacement.

**What I learned about the repository.** `scripts/` did not exist; I created
it for these three scripts. Running `conda run -n pypeit14 python` with the cwd
inside `PypeIt/pypeit/` shadows the package (`pypeit.py`), so scripts must be
run from this repo. `.claude/settings.json` allows WebFetch for
`www2.keck.hawaii.edu`; gemini.edu is blocked server-side, not by us. The
XTcalc tarball is a useful local copy of the Gemini sky models and should
probably be cached under a data directory in a later prompt (it is 46 MB, so
not in git).

### 2026-09-29 (Prompt #2: second round of MOSFIRE design Q&A)

Reread the doc: the Prompts section now has a `### Design` subsection with
prompts 1 and 2, and all 15 round-1 questions are answered "Agreed", with two
notes (Q3: the user will ask Josh Walawender whether the 5" slit was routine;
Q10: the user asked what UTR is). Appended a second round under the Design
Q&A after the user's answers, without editing them: a "Settled so far"
summary, the Q3 open item, the UTR explanation and recommendation (Q16), ten
new questions (Q17-26) on package layout, data formats and provenance,
combining standards into a current throughput, storage of the Gemini grid,
reduction workflow and the data root, the LSF model, slit-loss details,
testing, versioning for WMKO, and the definition of done, and a note that the
design doc can be drafted once these are answered.

UTR finding: the MOSFIRE headers define `SAMPMODE` 1:Single, 2:CDS, 3:MCDS,
4:UTR; the detector paper (Kulas et al. 2012, arXiv:1208.0314) states that
both MCDS and UTR are offered to observers and recommends MCDS for
spectroscopy, quoting lab read noise CDS 17.1-17.4, MCDS-4 8.9, -8 6.5, -16
4.9, -32 3.8, -64 3.3 e- (the Keck web table is a little higher: 21, 10.8,
7.7, 5.8, 4.2, 3.5, 3.0 e- through MCDS-128, presumably on-telescope values).
Keck's detector page does not list UTR. All on-sky frames we have are
MCDS-16; the dome flats are CDS. PypeIt never reads `SAMPMODE` or `NUMREADS`
(a grep of `spectrographs/`, `core/` and `images/` finds neither; only
`magellan_fire.py` and `mmt_mmirs.py` mention Fowler or up-the-ramp in
comments). Recommendation recorded: CDS and MCDS only in v1, schema fields
ready for UTR, decision revisited after the KOA `SAMPMODE` census.

New script: `scripts/size_gemini_sky_subset.py`, which reads the 24 Gemini
save files from the XTcalc tarball, cuts them to 0.95-2.45 um and reports the
float32 size at several samplings (45 MB native on disk; 7.2 MB at 0.02 nm,
1.4 MB at 0.1 nm for the MOSFIRE range; 1.4 MB / 0.6 MB for J only). This is
the basis of the Q20 default (0.05 nm, about 3 MB, committed to git).

What I learned about the repository: `docs/` now exists and is empty (created
by the user); `git status` shows `claude_prompts/keck_mosfire_prompts.md`
modified and `scripts/` untracked on branch `keck-mosfire`; there is no
`.gitattributes` and `.gitignore` has no rule for data files, so any data
policy (Q20, Q21) has to be added explicitly. `keck_etcs/` still holds only
`__init__.py` and `tests/__init__.py`, so the layout in Q17 starts from a
blank slate. No git commands were run other than `git status` and
`git branch`.

### 2026-09-29 (Prompt #3: design doc and implementation plan)

Reread the doc: Q16 "Agreed", Q17-26 "Use the default", so every round-1 and
round-2 default is now a decision; Q3 (5" slit routine?) still waits on Josh
Walawender. Wrote two documents.

`docs/keck_mosfire_design.md` (v0.1): 1 Purpose and scope; 2 Settled
decisions D1-D29 with rationale, plus eight decisions made while writing and
flagged for review (N1 Keck area 72.3674 m^2 from PypeIt rather than XTcalc's
75; N2 band window = filter half-power bandpass intersected with the 2048-pix
window at the long-slit position; N3 A0V fluxing by scaling PypeIt's Vega
spectrum to the star's 2MASS J in `keck_etcs.calib`, because
`VegaStandard` scales by V only; N4 sky-grid interpolation linear in airmass
and log PWV with clipping; N5 vacuum wavelengths throughout; N6 atmospheric
transmission applied to the source, not the sky; N7 exposure-time mode solves
the per-frame time at fixed `n_frames`; N8 the KOA search doc will be
`claude_prompts/koa_search_prompts.md`); 3 Instrument facts with sources;
4 Sensitivity analysis (KOA selection, workflow and data root, sensfunc and
telluric settings, metrics, per-era combination, trend analysis,
uncertainties); 5 ETC design (package layout, `compute(dict)->dict` with
input and output field tables, the physics with explicit equations for
signal, sky, LSF, stare and ABBA variance, S/N per pixel and per resolution
element, the exposure-time quadratic, and saturation; data files and
provenance; versioning); 6 Validation and testing; 7 Definition of done;
8 Open items; 9 References.

`docs/keck_mosfire_implementation.md` (v0.1): 18 steps S1-S18 in five
phases with a dependency map and parallel groups; each step has goal,
inputs, outputs, a verification check and dependencies, plus risks. Steps:
S1 data root and XTcalc cache; S2 telluric grid; S3 Gemini grid FITS; S4
reduce 2022-04-09; S5 LDS749B sensfunc; S6 harvest; S13 LSF from OH lines;
S7 core modules and schemas; S8 MOSFIRE instrument module and data files;
S9 `compute()`, CLI, regression fixtures; S10 throughput v0; S11 J0841
validation; S12 XTcalc comparison; S14 KOA search (own prompt doc); S15
batch reductions; S16 trend and first calibration release; S17 PypeIt
`ronoise` branch; S18 docs, README, CHANGES, WMKO note. Risks flagged: low
LDS749B S/N, PypeIt 2.0 API drift, wide-slit sample size, second-hand Gemini
provenance, network dependence, run time, regression churn.

New script: `scripts/mosfire_band_footprints.py`, which reads PypeIt's
`keck_mosfire_OH_*` and `keck_mosfire_arcs_*` wavelength templates and
reports per-band range and dispersion: Y 1.08, J 1.30, J2 1.30, H 1.63, K
2.17 A/pix, matching XTcalc. The templates span 2600-3000 pixels because they
are stitched across CSU slit positions, which is why the design defines the
band window from the filter and the 2048-pix detector (N2).

What I learned about the repository and PypeIt: PypeIt is 2.0.2.dev1217;
`pypeit_sensfunc` takes `--algorithm {UVIS,IR}`, `-s SENS_FILE`, `-o`;
`pypeit_setup -s -r -d -c`; `run_pypeit -r REDUX_PATH`; the `SensFunc`
datamodel holds `wave`, `zeropoint`, `throughput`, `airmass`, `exptime`,
`std_name`, `std_cal`, `std_ra/dec`, `telluric`, `algorithm`; the telluric
model table has `TELL_THETA` (pressure, temperature, water, airmass,
resolution, shift, stretch) and `TELL_PARAM`; spec1d objects carry `S2N`
(`med_s2n`), `FWHM`, `FWHMFIT`, `OPT_FLAM`, `OPT_FLAM_IVAR`, `OPT_COUNTS_SKY`,
`OPT_COUNTS_SIG_DET`, `BOX_NPIX`; `get_model_standard('A0', V_mag)` returns
`VegaStandard` scaled by V (hence N3). `docs/` was empty before this prompt.
No git commands were run.

### 2026-09-29 (Prompt #4: implementation prompt docs)

The prompt doc had moved to `claude_prompts/keck_mosfire/` (git shows the
rename staged); logging continues here. Split the 18 steps of
`docs/keck_mosfire_implementation.md` along its phase boundaries into six
numbered prompt docs in `claude_prompts/keck_mosfire/`, plus the KOA search
as its own top-level doc, per the project decision that the KOA search has
its own prompt doc and because LRIS will need the same doc later:

- `keck_mosfire_prompt_1.md`, Phase 0 foundations: S1 data root and XTcalc
  cache; S2 telluric grid; S3 Gemini grid FITS, including the decision-N5
  check (Gemini wavelengths vacuum or air, via OH-line positions against
  PypeIt's vacuum `OH_MOSFIRE_J` list).
- `keck_mosfire_prompt_2.md`, Phase 1 first sensfunc: S4 reduce 2022-04-09;
  S5 LDS749B sensfunc; S6 harvest; S13 LSF from OH lines.
- `keck_mosfire_prompt_3.md`, Phase 2 ETC core: S7 core modules and
  schemas; S8 MOSFIRE instrument module and data files; S9 `compute()`, CLI,
  regression fixtures (with a provisional XTcalc throughput if S10 has not
  run).
- `keck_mosfire_prompt_4.md`, Phase 3 validation: S10 throughput v0 and
  fixture regeneration; S11 J0841 validation, with the second N5 check
  against the measured J2 sky and the D14 sky-level check; S12 XTcalc
  comparison.
- `keck_mosfire_prompt_5.md`, Phase 4 time series: S15 split into S15a (A0V
  Vega+2MASS J support, batch driver, first batch) and S15b (remaining
  batches and harvest); S16 trend analysis and first calibration release.
- `keck_mosfire_prompt_6.md`, Phase 5 wrap-up: S17 PypeIt `ronoise` branch,
  preceded by an empirical CDS read-noise check from the lamp-off flats;
  S18 docs, README, CHANGES, WMKO API note.
- `claude_prompts/koa_search_prompts.md`: S14 as three MOSFIRE prompts
  (census and candidate table with the `SAMPMODE` histogram; first download
  batch; validation science frames) and an empty LRIS section for later.

Run order: 1 -> 2 -> 4 -> 5 -> 6, with 3 in parallel with 2 (after 1's S3),
the KOA doc in parallel from the start (needed before 5), and 6's S17 any
time after 3's S8. Every doc follows the house format (Goals, Context,
Prompts, Q&A, Logging, Logs), points at the design and plan sections by
number, lists the data root and the relevant scripts, restates the CLAUDE.md
rules where they bite (git by the user, `pypeit14`, scripts on disk, PypeIt
fixes on a PypeIt branch), carries the plan's risks into the prompts, and
ends each prompt with its verification check and "Log your work." Decisions
N1-N8 are written in as accepted, with verification sub-tasks where they
rest on assumptions (N5 in S3 and S11; the filter-curve air/vacuum question
in S8; the PypeIt custom-standard hook for N3 in S15a). No implementation
step was executed and no git commands were run other than `git status`.

What I learned: `claude_prompts/` now holds `starting_up.md`, the new
`koa_search_prompts.md` and the `keck_mosfire/` folder with the main prompt
doc and six part docs; the main doc's Context still points at the dev-suite
raw data and the Keck ETC page, so the part docs carry their own fuller
Context sections.