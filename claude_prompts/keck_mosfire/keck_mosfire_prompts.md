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

5. Ok, I have one significant change for the design and implementation plan. 
I wish to perform the data reduction within Nautilus.  Please examine the code and files in
the `Oceanography/python/PAB/nautilus/` folder to see how I have performed such work 
previously.  Then modify the design and implementation plans to reflect this change.
Use Fable if you can.  Log your work.

6. I have answered your questions about Nautilus below.  Please read the answers and make updates to the design, plan, and prompt docs.
Use Fable if you can.  Log your work.

## Registry

*2026-09-30. One-time setup of the container registry for the keck-etcs image
(D31; plan steps S0 item 4 and S4a). It is the same procedure you followed for
`profx/pab` in July (PAB `claude_prompts/nautilus_prompts.md`, Container
section). Your part is steps 1-4. Step 5 happens in S4a.*

**Status (2026-09-30):** steps 1-4 done by the user, who reported success.
Deploy-token username `gitlab+deploy-token-1383`; the token itself stays with
the user. Registry path as below, project Public. Step 5 is next, in S4a.

**Target:** `gitlab-registry.nrp-nautilus.io/profx/keck-etcs`, a **public**
image, so pods in namespace `pypeit` pull it without an `imagePullSecret`.

1. **Create the GitLab project.** Sign in at `https://gitlab.nrp-nautilus.io`
   and choose New project, then Create blank project:
   - Project name `keck-etcs`, namespace `profx` (your user).
   - Visibility level **Public**. The repository stays empty; the project is
     only a home for the registry, so leave the README unchecked (or check
     it, it doesn't matter).
   - After creating it, open Settings, General, "Visibility, project features,
     permissions" and confirm **Container registry** is enabled and visible to
     "Everyone with access". Otherwise anonymous pulls from pods fail.
   - Check: Deploy, Container Registry in the left sidebar shows an empty
     registry at the path above.

2. **Create a deploy token.** In the project, go to Settings, Repository,
   Deploy tokens, then Add token:
   - Name `keck-etcs-build`. Set no expiry, or one after the MOSFIRE
     milestone.
   - Scopes: **`read_registry`** and **`write_registry`** only.
   - Copy the token **username** (e.g. `gitlab+deploy-token-NNN`) and the
     **token** into your password manager. GitLab shows the token only once.
   - A Personal Access Token with `write_registry` also works, but a deploy
     token is limited to this one project, which is safer.

3. **Log in on the build host** (the Linux workstation, D31). Use stdin so the
   token stays out of shell history and `ps`:
   ```bash
   docker --version     # confirm docker is installed
   printf '%s' '<token>' | docker login gitlab-registry.nrp-nautilus.io \
       -u 'gitlab+deploy-token-NNN' --password-stdin
   ```
   The expected output is `Login Succeeded`. The credential lands in
   `~/.docker/config.json` on the workstation, which you were already logged
   into for `profx/pab`. A deploy token is per project, so this is a new login
   for `keck-etcs`. It replaces the PAB entry for the same registry host, and
   that is fine: to push PAB again, log in with the PAB token.

4. **Tell me when it's done**, and confirm (a) the exact registry path, if it
   differs from the one above, and (b) that the project is Public. **Do not**
   paste the token anywhere in this repository or in chat.

5. **(S4a, done by me with you at the workstation.)** `nautilus/build_image.sh`
   builds and smoke-tests `profx/keck-etcs:0.1.0`. With `--push` it runs
   ```bash
   docker push gitlab-registry.nrp-nautilus.io/profx/keck-etcs:0.1.0
   docker manifest inspect gitlab-registry.nrp-nautilus.io/profx/keck-etcs:0.1.0
   ```
   and records the digest in the job YAML header. An anonymous pull from the
   cluster (the S1b inspect pod, with the image swapped in) confirms that pods
   can fetch it.

**Things to know**
- **The image is public; the bucket is private.** Nothing secret goes into the
  image: no S3 keys and no `.netrc`. Pods get S3 credentials only by mounting
  the Kubernetes secret at run time (D32). `build_image.sh` will refuse to
  build if a credentials file is in the build context.
- **Registry hangs.** The NRP registry has hung on manifest writes before.
  If a `docker push` stalls for more than about 10 minutes on "Waiting" or at
  the manifest step, interrupt it and push again. Layers already uploaded are
  skipped. Then confirm with `docker manifest inspect`.
- **Tags.** Semantic versions (`0.1.0` for the dry run, `0.2.0` before the
  batches) plus `latest`. Jobs reference the explicit tag, never `latest`, and
  carry the digest in a comment (PAB convention).
- **Revoking.** If the token leaks, revoke it under Settings, Repository,
  Deploy tokens and repeat steps 2-3. Already-pushed images are unaffected.

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

### (d) Reductions on Nautilus

*2026-09-30, after Prompt #5. These are the decisions that moving the
reductions to Nautilus left for you (design doc v0.2, section 8, and decisions
N9-N16 in section 2; detail in section 4.8). As before, each ends with my
recommended default, so "agree" is a complete answer.*

27. **Namespace.** `pypeit` (the dev-suite namespace, where
    `prp-s3-credentials` already exists) or `sea-meets-the-stars` (PAB)?
    *Default:* `pypeit`.
>A. Default

28. **S3 bucket.** A new bucket `keck-etcs` with a public-read policy like
    `pab`'s, or a prefix inside the existing `pypeit` bucket? The `pypeit`
    bucket's policy allows anonymous `PutObject`/`DeleteObject`, so anyone
    could overwrite our products there. *Default:* a new bucket `keck-etcs`,
    public-read only, writes need credentials.
>A. A new bucket named `keck-etcs`.  I have created it.  Only I have read/write access for now 

29. **Container registry.** `gitlab-registry.nrp-nautilus.io/profx/keck-etcs`,
    public, same as `profx/pab`. This needs you to create the GitLab project
    and a deploy token with `write_registry` once. *Default:* yes, that path.
>A. Default

30. **Build host.** This Mac has no `docker`. Build on the Linux workstation
    as you did for PAB, or install `colima`/`podman` here? *Default:* the
    workstation (plan step S4a assumes it).
>A. Default

31. **Python in the image.** `python:3.12` (what the dev suite and PAB use,
    and the safest for wheels) or `python:3.14` (matches the local `pypeit14`
    env)? PypeIt is pinned to the same commit either way. *Default:* 3.12, and
    switch to 3.14 if the dry run shows any numerical difference from the
    local reduction.
>A. Default

32. **Backup.** Nautilus is not backed up. `rclone` the bucket's `harvest/`
    and `sens/` prefixes to `AIOcean:` at each calibration release? *Default:*
    yes, at release time only. The committed ECSV products are the primary
    record.
>A. Backup only the high-level products needed for the sensitivity analysis and the ETC.

33. **KOA downloads (N15).** Run the raw-frame downloads as a Nautilus Job
    that writes straight to S3, with the metadata search staying local? This
    depends on pods reaching `koa.ipac.caltech.edu` and `pykoa`'s anonymous
    download of public data working without a login, which step S14b checks
    first. *Default:* in-cluster, with local download and push as the
    fallback.
>A. Default

34. **One night per pod (N11).** An Indexed Job with one pod per night,
    `parallelism` 4 to start. In PAB you kept to one pod because of the single
    SQLite writer. PypeIt nights share no writer, so fanning out is safe.
    *Default:* Indexed Job, one night per pod.
>A. Default

35. **No PVC (N10).** Pods work on `emptyDir` scratch and push to S3. S3 is the
    canonical store and `$KECK_ETCS_DATA` is a local mirror synced by
    `scripts/nautilus/s3_sync.py`. No CephFS PVC, given PAB's SQLite-on-CephFS
    hangs and PypeIt's many small files. *Default:* agreed, no PVC. A small
    one can be added later for inspection only.
>A. Default

36. **Harvest in the pod (N12).** Each night job harvests its own `sens_*.fits`
    and pushes the per-standard row and curve, and a local `--merge` builds
    `standards.ecsv`. *Default:* agreed.
>A. Default
37. **Local reference as the gate (N13).** Reduce 2022-04-09 once locally.
    The Nautilus dry run must reproduce the LDS749B zero point to within 1
    percent over 1.117-1.260 um before any batch runs. All other nights are
    reduced on Nautilus only. *Default:* agreed, 1 percent tolerance.
>A. Default
38. **Image contents and provenance (N9, N14).** PypeIt installed from GitHub
    at the local commit (`017bece06`, currently on `origin/orig-hires-fixes`),
    the MOSFIRE and telluric caches baked in at build time, and git SHAs
    baked in as `KECK_ETCS_GIT_SHAS`. Every product records `image`,
    `image_digest`, `pypeit_git_sha`, `keck_etcs_git_sha`, `job_name` and
    `s3_prefix`. One question inside this: pin to a commit on
    `orig-hires-fixes`, or wait for it to merge and pin to `develop`?
    *Default:* pin the current commit now and re-pin at the first calibration
    release.
>A. This work will not need the `orig-hires-fixes` branch.  Have our work use the `develop` branch.

39. **What stays local (N16).** The ETC core, `compute()`, schemas, tests, the
    Gemini grid build, combine, trend, the J0841 validation and the XTcalc
    comparison all run locally on synced products. Pods never call
    `compute()`. *Default:* agreed.
>A. Default

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

### 2026-09-30 (Prompt #5: move reductions to Nautilus)

Read every file in `Oceanography/python/PAB/nautilus/` (26 files: the
`*_job.yaml` manifests, `build_image.sh`, the helper scripts, the CSVs),
PAB's `Dockerfile`, `HOWTO.md`, `CLAUDE.md`, `README.md` and
`claude_prompts/nautilus_prompts.md`, then the PypeIt dev suite's own
`nautilus/` folder (`gen_kube_devsuite`, `kube_dev_suite.yaml`,
`full_dev_suite_6cpu.yaml`, `README_s3`, `s3_pypeit_policy.json`,
`rclone.conf`, `README_gdrive`), and PypeIt's `pypeit/pkg/cache.py`,
`pypeit/pkg/pypeitdata.py`, `pypeit/data/s3_url.txt` and the
`install_telluric` / `cache_github_data` scripts. Then bumped both design
documents to v0.2 with change notes. No git commands other than `git status`,
`git log`, `git branch -r --contains` and `git remote -v`; no scripts written
(this prompt is planning only; the plan's S1b, S4a, S4b, S14b and S15 name
the scripts and manifests to write).

**Design doc (`docs/keck_mosfire_design.md` v0.2).** New user decision D30
(reductions and KOA downloads as Nautilus Jobs; ETC library, tests,
combine/trend/validation and the KOA metadata search stay local). Section
4.2 rewritten around an S3 bucket layout that mirrors the data root
(`mosfire/<YYYYMMDD>/{raw,redux,sens,harvest}`, `run_manifest.json`,
`manifests/`, `runs/<job>/status.ecsv`), with `$KECK_ETCS_DATA` as the local
mirror filled by `scripts/nautilus/s3_sync.py`. Section 4.3 corrected:
PypeIt's telluric "S3 host" is Nautilus S3 itself. Section 4.4 gains six
provenance columns. New section 4.8 (conventions carried over, image,
storage, jobs, provenance, failure handling, dry run and gates, what stays
local). 5.1 layout gains `nautilus/` and `scripts/nautilus/`; 5.4 and 5.5
carry the image tags into product `meta` and `CHANGES.md`. New flagged
decisions N9-N16: image pinned to the local PypeIt commit with the cache
baked in (N9); S3 canonical plus `emptyDir` scratch, no PVC (N10); one night
per pod as an Indexed Job (N11, a deliberate departure from PAB's single
pod, justified because PypeIt nights share no writer); harvest in the pod
plus a local merge (N12); one local reference reduction of 2022-04-09 as
the dry-run gate (N13); provenance fields (N14); KOA downloads in-cluster
(N15); the local/remote split (N16). Section 8 lists the user's calls with
recommended defaults: namespace (`pypeit`), bucket (new `keck-etcs`,
public-read only), registry path (`profx/keck-etcs`), build host (the Linux
workstation; this Mac has no `docker`), base Python (3.12 vs 3.14), backup
of the bucket to `AIOcean:` at release time, KOA reachability from pods.

**Implementation plan (`docs/keck_mosfire_implementation.md` v0.2).** S1-S18
keep their numbers; new suffixed steps S1b (bucket, secrets check,
`s3_sync.py`, bucket policy, inspect pod, push the 2022-04-09 raw frames),
S4a (`nautilus/Dockerfile`, `build_image.sh`, `keck_etcs/provenance.py`,
build guards), S4b (`night_job.yaml` Indexed template, `validate_job.yaml`,
`gates.py`, `night_failures.py`, `status_table.py`, the dry run gated
against the local S4 reference to 1 percent in zero point), S14b
(`koa_download_job.yaml`, `download_mosfire_night.py --to-s3`). Re-scoped in
place: S2 (records the grid sha256 for the image guard; API is
`dataPaths.telgrid`, not `tel_model`), S4 (local reference; the driver is
designed as the in-pod driver with `--scratch`/`--s3-*` hooks), S5, S6
(harvest module runs in-pod, `--merge` locally), S13 and S11 (synced
inputs), S14 (metadata only, plus night manifests), S15 (S15a pilot, S15b
batches and sweeps, S15c sync and merge), S16, S17 and S18 (operator guide
in `nautilus/README.md`). Dependency map, parallel groups, verification
checks and the risks section updated (local-versus-in-pod agreement, image
and registry, no-PVC trade-off, secrets and outward-facing actions, sizing
from the pilot).

**What I learned about the user's Nautilus workflow.** PAB: namespace
`sea-meets-the-stars`; public image `gitlab-registry.nrp-nautilus.io/profx/pab:<semver>`
built by `build_image.sh [--push]` from a staged rsync context with
third-party deps in a separate first layer, git SHAs baked in as
`PAB_GIT_SHAS` (ENV + OCI label) because the image has no `.git`, behavioural
build guards, and a bounded `--rm` smoke test; the user does `docker login`
with a deploy token; the NRP registry has hung on manifest writes. Storage:
CephFS PVC `pab-data` (storage class `rook-cephfs`, not `cephfs`) at
`/data` with per-version subdirectories, plus Nautilus S3 (Ceph RGW,
path-style, `https://s3-west.nrp-nautilus.io`, public-read bucket `pab`)
pushed by a boto3 helper mounted as a ConfigMap because the image ships no
`aws` CLI; SQLite on CephFS hard-hangs, fixed by a DB-local `emptyDir` copy
with a periodic file-copy checkpoint; Nautilus is not backed up, so releases
are rcloned to `AIOcean:`. Jobs: one `batch/v1` Job per stage, one pod,
in-process parallelism (the user explicitly asked "why multiple pods" and
the answer was the single SQLite writer), `restartPolicy: Never`,
`backoffLimit: 4` for resumable stages and `0` for one-shots,
`activeDeadlineSeconds` after an exit hang, `imagePullPolicy: Always`, image
digest in a comment, `bash -lc` with a literal `|` block (a folded `>` block
broke a here-doc once; one-line `python -c` only), `set -o pipefail`, a
`log()` helper tee'd to the PVC, a PROVENANCE block first, counts before and
after, `du -sh`, a `*_DONE` sentinel, `exit 1` on stage failure, `ulimit -n`
and `MALLOC_ARENA_MAX` where earned, node affinity to west-coast nodes for
network-bound stages, secrets `earthdata-netrc` and `prp-s3-credentials`
mounted by subPath, and a header comment with purpose, sizing from measured
rates ("take the rate from a few hundred in, not the first fifty") and the
three `kubectl` lines. Failures: idempotent stages re-applied; targeted
subset CSVs (`rediscover_csv.py`, `sweep_stalled.csv`); failure-list
scripts for the user to chase; gate scripts that exit non-zero
(`v2_validate_gates.py`, which also learned to check artefacts, not just the
database); a 5-profile validate, a stratified 1k pilot, then the full run.
Dev suite: namespace `pypeit`, bucket `s3://pypeit` (in-cluster endpoint
`http://rook-ceph-rgw-nautiluss3.rook`; its policy allows anonymous
Put/Delete), everything on `emptyDir` ephemeral storage with results pushed
to S3 by `awscli` installed in the pod, PypeIt installed at run time from a
git branch, telluric grids copied from `s3://pypeit/telluric/atm_grids/`,
raw data from S3 or Google Drive via a service-account rclone remote.

**What I learned about the repository and PypeIt.** `pypeit14` is Python
3.14.6 with PypeIt `2.0.2.dev1217+g017bece06` as an editable install of
`/Users/xavier/Projects/PypeIt/PypeIt`, clean, on branch `orig-hires-fixes`
whose HEAD is on `origin`, so the image can pin that commit from GitHub.
PypeIt allows Python 3.11-3.14. PypeIt's `s3_url.txt` is
`s3-west.nrp-nautilus.io`, so the "S3 host" of S2 is Nautilus and the grid
is the public object `s3://pypeit/telluric/atm_grids/TellPCA_3000_26000_R10000.fits`;
the cache is astropy's (`~/.cache/pypeit` here, `XDG_CACHE_HOME` overrides
it); `pypeit_install_telluric` and `pypeit_cache_github_data keck_mosfire`
populate it offline; the telluric path is `dataPaths.telgrid` (host
`s3_cloud`), not `tel_model`. This Mac has `kubectl` (context `nautilus`)
and `rclone` (remotes `GDrive:`, `AIOcean:`, `nautilus_s3:`, `whn:`) but no
`docker`. The repo still has only `keck_etcs/__init__.py`, `scripts/`, the
docs and prompt docs; `git status` shows only this prompt doc modified.

**Part prompt docs that need revision to match v0.2** (not edited in this
prompt): `keck_mosfire_prompt_1.md` (S1 adds `paths.s3_prefix`; new S1b
prompt; S2 records the sha256 and uses `dataPaths.telgrid`);
`keck_mosfire_prompt_2.md` (S4 becomes the local reference with the S3
hooks; new S4a and S4b prompts; S5, S6 and S13 read synced products and S6
gains the in-pod and `--merge` modes); `keck_mosfire_prompt_3.md` (note
only: S8's filter curves must land before the `0.2.0` image build);
`keck_mosfire_prompt_4.md` (S11 inputs come from `s3_sync.py pull`);
`keck_mosfire_prompt_5.md` (S15 rewritten as Indexed Jobs, pilot, sweeps
and sync; S16 lists image tags in `CHANGES.md`);
`keck_mosfire_prompt_6.md` (S17 may re-pin the image; S18 writes the
`nautilus/README.md` operator guide); `koa_search_prompts.md` (prompt 2 and
3 downloads become the in-cluster S14b Job writing to S3, with a local
fallback; prompt 1 also emits the night manifests).
### 2026-09-30 (Nautilus decisions posed as Q&A)

At the user's request (a follow-up to Prompt #5, not a numbered prompt),
turned the Nautilus decisions left open in design doc v0.2 into questions
Q27-Q39 under a new Q&A subsection "(d) Reductions on Nautilus". Q27-Q33 are
the seven open items from design section 8: namespace, bucket, registry, build
host, base Python, backup and KOA downloads. Q34-Q39 ask for review of the
flagged decisions N9-N16. Each question gives the recommended default. The
design and implementation docs were not changed; once the user answers, the
docs should be updated (N-decisions promoted to settled D-decisions, section 8
trimmed). No git commands were run.

What I learned: the Q&A numbering is continuous across subsections (1-26 in
(a)-(c)), and the user answers inline with `>A.` lines, so the new questions
continue at 27 and leave room for those lines.

### 2026-09-30 (Prompt #6: apply Nautilus answers)

Read the answers to Q27-Q39 in subsection (d). Ten are the recommended
defaults (namespace `pypeit`; registry `profx/keck-etcs`; build on the Linux
workstation; `python:3.12`; in-cluster KOA downloads with a local fallback;
Indexed Job, one night per pod; no PVC; harvest in the pod; the local
reference as the 1 percent gate; the local/remote split). Three changed:
Q28, the bucket `keck-etcs` exists, created by the user, and is **private**
(only the user has read/write); Q32, back up only the high-level products
needed for the sensitivity analysis and the ETC; Q38, this work does not use
`orig-hires-fixes`, PypeIt comes from `develop`. Applied them to both design
docs and all seven part prompt docs. No git commands other than read-only
inspection (`git status`, `git branch --list`, `git rev-parse`, `git log`,
`git ls-remote`, `git merge-base`, `git describe` on the PypeIt checkout);
no scripts written (planning only); nothing in this file changed except this
entry.

**Design doc v0.3.** The eight flagged decisions of v0.2 are promoted to
settled decisions **D31-D38** in the section 2 table (image; storage; job
granularity; harvest in the pod; local reference gate; provenance fields;
KOA downloads; what stays local), with the three changes folded in, and
**D39** added for the backup set. All cross-references in 4.2, 4.3, 4.4,
4.8 and 5.4 were renumbered to the D-numbers. Section 4.2 names the private
bucket and its credential implications; 4.8.1 notes that PAB's bucket is
public but ours is not; 4.8.2 now pins PypeIt through a single file
`nautilus/pypeit_pin.txt` on `develop` (`f3a1f1d274b1...` =
`origin/develop` on 2026-09-30, `git describe` 2.0.1-1216, expected version
`2.0.2.dev1216+gf3a1f1d27`), built on the workstation, with the registry
project and deploy token as the user's one-time actions; 4.8.3 spells out
who needs credentials (local `s3_sync.py`, pods via `KECK_ETCS_S3_SECRET`,
nobody else: products ship in git) and drops the public-read policy, leaving
wider access as an optional later item; 4.8.4 fixes the namespace; the old
4.8.9 is now the backup section (included/excluded table, per-batch and
per-release timing, `AIOcean:keck-etcs/` and
`AIOcean:keck-etcs/releases/<calib_version>/`) and 4.8.10 points at the
residual items. Section 8's Nautilus block is now verifications and
one-time user actions tied to plan steps (S0 checkout on `develop`; S1b
credentials secret; S4a registry; S14b KOA reachability; S4b base-Python
revisit; optional wider bucket access).

**Implementation plan v0.3.** New step **S0** (user prerequisites and the
pin check: switch the PypeIt checkout to `develop` at the pin, re-run `pip
install -e ".[dev]"` in `pypeit14` if `pypeit.__version__` still reports
`g017bece06`, confirm the local AWS profile lists the bucket, create the
GitLab project and deploy token; outputs `nautilus/pypeit_pin.txt` and
`scripts/check_pypeit_pin.py`). S1b loses the bucket-policy deliverable and
gains the credentials test (the inspect pod listing the bucket with the
mounted secret decides between `prp-s3-credentials` and a new
`keck-etcs-s3-credentials`); `s3_sync.py` fails hard on `AccessDenied`. S4
refuses to run unless the pin check passes. S4a installs PypeIt from the
pin file, refuses to build a pin that is not on `develop`'s history, and
records tag, digest and pin. S4b mounts the secret for the pull too, and
`gates.py --reference` asserts equal PypeIt SHAs before comparing. S14b
starts with a reachability probe. S15b runs `scripts/nautilus/backup_products.py`
after each batch; S16 runs it again in `--release` mode. S17's branch comes
off `develop`; a feature-branch pin needs `--allow-branch`. S18's operator
guide covers the pin, the private bucket and the backup. Risks rewritten
for `develop` drift, the private bucket and the backup set. Step numbers
S1-S18 and the v0.2 suffixes are unchanged; S0 is new and precedes S1.

**Part prompt docs.** None had been executed (no Log entries, no Q&A), so
the prompts were revised in place, keeping the house format and the
existing prompt numbers: `keck_mosfire_prompt_1.md` (S1 adds
`paths.s3_prefix` and the bucket constant; S2 uses `dataPaths.telgrid` and
writes `nautilus/telluric_grid.sha256`; new prompt 4 = S0 check + S1b);
`keck_mosfire_prompt_2.md` (S4 is the local reference on the pin with the
S3 hooks; S5 ships the `.sens` file in the image and compares local and
in-pod sensfuncs; S6 has `harvest` and `--merge` modes and the six
provenance columns; S13 pulls `Calibrations/` while it is on S3; new prompts
5 = S4a and 6 = S4b, with the run order 1 -> 5 -> 6 -> 2 -> 3 stated);
`keck_mosfire_prompt_3.md` (scheduling note that S8 precedes the `0.2.0`
image; S9 verifies no PypeIt/boto3/network import); `keck_mosfire_prompt_4.md`
(S11 pulls the dry run's spec2d before relying on the backup; S10 records
image tags in the era `meta` and `CHANGES.md`); `keck_mosfire_prompt_5.md`
(S15a image rebuild and pilot; S15b batches, sweeps and per-batch backup
with the new `backup_products.py`; S15c sync and merge; S16 release backup);
`keck_mosfire_prompt_6.md` (S17 branch off `develop`; S18 operator guide
with pin, private bucket and backup); `koa_search_prompts.md` (prompt 1
also writes the night manifests; prompt 2 is the in-cluster S14b Job with a
reachability probe and the local fallback; prompt 3 marks validation nights
`spec2d = 1`).

**Judgment calls flagged for the user.** (1) Backup set: all `spec1d_*`
files are included (small; S11 needs the science ones) and
`Calibrations/WaveCalib*` are excluded (S13 commits its measurements; a
re-reduction regenerates them); backups run after each S15 batch and at
each release, to `AIOcean:keck-etcs/`. (2) The default pod secret is
`prp-s3-credentials` in namespace `pypeit`, but whether it holds keys that
can read the private bucket is unknown; the S1b inspect-pod test decides,
and the fallback is a new `keck-etcs-s3-credentials` secret. (3) The pin is
`origin/develop` as of 2026-09-30 (`f3a1f1d27`); if the user pulls a newer
`develop` before S0, the pin file follows HEAD. (4) `build_image.sh`
refuses pins off `develop`'s history unless `--allow-branch` is passed, so
a `ronoise` feature-branch image is possible but deliberate.

**What I learned.** The local PypeIt checkout already has a `develop`
branch and `origin/develop` is `f3a1f1d27` (2026-09-14, "Merge pull request
#2197"), identical to the remote's head per `git ls-remote`, so no fetch is
needed to pin it; `orig-hires-fixes` (`017bece06`) is one commit beyond a
different base, hence the `dev1217` versus `dev1216` version strings. An
editable PypeIt install keeps `pypeit/pkg/version.py` from install time, so
switching branches does not update `pypeit.__version__` until `pip install
-e` is re-run: the S0 check covers that. `git rev-parse` of two refs in one
call failed with "Needed a single revision" while each ref resolves alone;
not investigated. No part prompt doc had a Log or Q&A entry, so nothing had
to be preserved as executed.

### 2026-09-30 (Registry instructions)

At the user's request (a follow-up to Prompt #6, not a numbered prompt),
filled the new `## Registry` section with one-time instructions for the
`gitlab-registry.nrp-nautilus.io/profx/keck-etcs` registry: create a public
GitLab project with the container registry enabled; create a project deploy
token with `read_registry`/`write_registry`; `docker login --password-stdin`
on the Linux workstation; report back without sharing the token. It also
covers what S4a does next (build, push, `docker manifest inspect`, anonymous
pull test from the cluster), keeping secrets out of the public image,
retrying stalled pushes, tag policy and revoking the token. These follow the
PAB Container section (`PAB/claude_prompts/nautilus_prompts.md`) and PAB's
`build_image.sh`. One new commitment for S4a: `build_image.sh` refuses to
build if a credentials file is in the build context.

The user also settled two S0 items. Credentials are fine as they are. The
laptop's PypeIt checkout **stays on `orig-hires-fixes`**. That conflicts with
the v0.3 plan: S0 and S4 require the local reference reduction to run on the
image's `develop` pin, and the S4b gate asserts equal PypeIt SHAs. This is
raised with the user for a decision; the design and plan docs are not yet
changed. No git commands were run.

### 2026-09-30 (Registry set up)

The user reported that registry steps 1-4 succeeded: the project
`profx/keck-etcs` was created and a deploy token made, with username
`gitlab+deploy-token-1383`. Recorded as a status line in `## Registry`. Only
the token username is in the repo; the token stays with the user. S0 item 4 is
done. Still open: how the S4 local reference handles the laptop staying on
`orig-hires-fixes` (see the previous entry).

### 2026-09-30 (Pin check relaxed to MOSFIRE-equivalence)

Resolves the open item of the two previous entries: the laptop's PypeIt
checkout stays on `orig-hires-fixes` in `pypeit14` and no PypeIt
development happens on this laptop (user decision). Facts checked
read-only: `git merge-base HEAD origin/develop` is the image pin
`f3a1f1d27`; HEAD `017bece06` is one commit ahead and none behind; `git
diff --stat origin/develop...HEAD` touches only
`pypeit/spectrographs/keck_hires.py` (+131/-33). The local MOSFIRE code
path is therefore identical to the pin, so requiring equal SHAs would force
a branch switch for no gain.

Changes (design and plan bumped to v0.3.1 with a dated change note; no
other file edited except the part docs listed and this log; no git
commands other than read-only inspection):

- `docs/keck_mosfire_design.md`: D35 rewritten. The requirement is now
  "the local checkout contains the pin and differs from it only in paths
  irrelevant to MOSFIRE J reductions": `scripts/check_pypeit_pin.py` passes
  if (1) `git merge-base --is-ancestor <pin> HEAD` and (2) `git diff
  --name-only <pin> HEAD` plus uncommitted changes match an allow-list
  (`pypeit/spectrographs/*.py` except `keck_mosfire.py`, `spectrograph.py`,
  `util.py`, `__init__.py`; `doc/`; `*.rst`; tests), reporting both SHAs
  and the file list and naming offenders on failure. 4.8.2 says S0 checks
  containment, not identity. 4.8.5 adds `pypeit_pin` and `pin_check` to the
  provenance fields. 4.8.7's gate first requires the reference's recorded
  pin to equal the image's PypeIt SHA with a passed check, then the 1
  percent comparison. Section 8: the "switch to develop / reinstall" item is
  replaced by a check-only item that says what happens when a future pin
  changes MOSFIRE code (the check fails by design; the user updates the
  laptop checkout or the reference is redone on the workstation);
  credentials marked confirmed by the user; registry marked done (project
  `profx/keck-etcs`, deploy-token username `gitlab+deploy-token-1383`,
  `docker login` on the workstation).
- `docs/keck_mosfire_implementation.md`: S0 no longer asks the user to
  switch or reinstall; it records the done prerequisites and the checked
  facts, adds `nautilus/pypeit_pin_allowlist.txt`, specifies the check's
  two tests, its JSON result and a negative test, and notes the local
  version string will keep reporting `dev1217+g017bece06`. S4 copies
  `pypeit_pin`/`pin_check` into `run_manifest.json`; S4a's `--image` check
  requires the image SHA to equal the pin and only reports the local SHA;
  S4b's `gates.py --reference` compares pins and check results, not SHAs;
  S11 wording; S17 states the branch is made off `develop` on the
  workstation, with the change prepared here as
  `nautilus/patches/pypeit_mosfire_ronoise.patch` plus the test file; the
  drift risk rewritten around containment and the allow-list.
- `keck_mosfire_prompt_1.md` (Context and prompt 4: no switch/reinstall,
  prerequisites done, the allow-list file, the two-part check, the negative
  test), `keck_mosfire_prompt_2.md` (Context pin bullet; API-name note
  simplified since only `keck_hires.py` differs; S4 failure guidance;
  `run_manifest.json` fields; S4a `--image`; S4b gate on pins),
  `keck_mosfire_prompt_4.md` (Context), `keck_mosfire_prompt_5.md`
  (API-name note simplified), `keck_mosfire_prompt_6.md` (Context; S17
  done off `develop` on the workstation via a patch file; consequence of a
  pin that changes `keck_mosfire.py`). `keck_mosfire_prompt_3.md` and
  `koa_search_prompts.md` needed no change.

Judgment calls: the allow-list lives in a file (`nautilus/pypeit_pin_allowlist.txt`)
so a future exception is a reviewed edit, not a code change; the S17 change
is delivered as a patch file plus test file in this repo, since the session
cannot edit the workstation checkout and must not edit the laptop one.

What I learned: the pin equals the merge-base, so `orig-hires-fixes` is a
clean one-commit branch off today's `develop`, and the two version strings
(`dev1217` local, `dev1216` image) differ by exactly that commit. In-pod
provenance is unaffected: pods run the pin exactly, so for them
`pypeit_git_sha == pypeit_pin` and the diff list is empty. The Logs had
grown two entries ("Registry instructions", "Registry set up") after the
Prompt #6 entry; this entry was first inserted before them by anchoring on
the Prompt #6 text and was moved here so the log stays chronological.
