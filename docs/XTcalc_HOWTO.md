# Running the Keck XTcalc ETC (MOSFIRE)

Purpose: run the original IDL XTcalc v2.3 (G. Rudie 2012) once, to check
our Python port (`scripts/mosfire/compare_xtcalc.py`) and the band-median
quirk described in `docs/keck_mosfire_design.md` Appendix A
(`claude_prompts/keck_mosfire/keck_mosfire_prompt_4.md`, Q&A S12 item 1).

## 1. Get the code and data

Either copy the unpacked directory from the workstation:

```
rsync -a <workstation>:~/Projects/PypeIt/keck-etcs-data/external/xtcalc/XTcalc_dir ~/XTcalc_dir
```

or download and unpack the original tarball:
`https://www2.keck.hawaii.edu/inst/mosfire/XTcalc.tar`.

Then set the one required environment variable (the manual,
`XTcalc_dir/MOSFIRE_XTcalc.pdf`, section 1.1):

```
export MOSFIRE_XTCALC=~/XTcalc_dir
```

Do not use the bundled `XTcalc` csh launcher. It hard-codes Caltech's IDL
8.1 path and license server.

## 2a. GUI through the IDL Virtual Machine (no license needed)

The Virtual Machine ships with any IDL install. It can also be downloaded
free from NV5 Geospatial (formerly Harris/Exelis); that needs an account.

```
cd ~/XTcalc_dir
idl -vm=run_XTcalc.sav
```

In the GUI:

- Atmospheric Window **J**
- Slit Width **0.7**, Angular extent **0.7**, Number of Exp. **4**, Fowler
  Sampling **16**
- **Use Magnitude**: **20.0**, **AB**, Type of Spectrum **Flat F_nu**
- **Determine Signal to Noise**, Total Exposure Time **480**
- Airmass and water vapour: **Use Default** (airmass 1.0, 1.6 mm)
- Click **Calculate**, then read the **S/N** row of the output table.

## 2b. Command line with licensed IDL (no GUI)

This needs the IDL Astronomy Library (astrolib) on the IDL path, for
`readcol`.

```
cd ~/XTcalc_dir/bin
idl
IDL> .r XTcalc
IDL> XTcalc, 'J', 0.7, 16, 0.7, 4, mag=20.0, /AB, time=480
```

The positional arguments are band, slit width, reads, angular extent and
number of exposures. The results table, including an "S/N" line, prints to
the terminal.

## 3. What to compare

| Case | XTcalc S/N | Meaning |
|---|---|---|
| J = 20 AB, 0.7"/0.7", 4 exp, 16 reads, 480 s | **≈ 4.44** | the band-median quirk is real (our port, as coded) |
| same | **≈ 7.39** | no quirk: XTcalc takes a true band median |
| same | anything else | send the full printed table |

A second check, the manual's own Figure 1 example (line mode, which the
quirk does not affect):

```
IDL> XTcalc, 'K', 0.7, 16, 0.7, 1, lineF=9.0, lineW=6563, /Angstroms, FWHM=30, z=2.3, time=1000
```

In the GUI the same case is: K band; 0.7/0.7; 1 exposure; 16 reads;
**Use Line Flux** with 9.0, 6563 Angstroms, redshift 2.3, source FWHM 30
km/s; total time 1000 s. The manual shows S/N **9.1** (GUI v1.8); our port
gives **8.85**.

## 4. Report back

Put the numbers under Q&A S12 item 1 in
`claude_prompts/keck_mosfire/keck_mosfire_prompt_4.md`. Appendix A of the
design doc is then updated from "inferred from the source" to "confirmed"
(or corrected).

## Result (2026-10-05)

The XTcalc GUI at WMKO, run with the J configuration above, reported
**S/N 4.4 per spectral pixel**, matching the port's 4.437. The band-median
quirk is confirmed (design Appendix A).
