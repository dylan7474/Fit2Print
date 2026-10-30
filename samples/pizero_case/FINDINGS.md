# What the sample taught us (2026-10-30)

Purpose of this sample: find out which stages and checks of Fit2Print work on a project that is NOT the Phonosphere radio, and what is missing.

## Design problems the tools found (and the fix)
| Found by | Problem | Fix |
|---|---|---|
| `fit2print overhang` (bridge vs cantilever) | the snap windows ran into the USB/HDMI openings: a 21 mm bridge and a 6 mm cantilever | hooks moved to the end walls (no ports) |
| `snap.check` | hooks 7 mm long bent 0.8 mm: 2.9 % strain, over the 2 % limit (shortest passing hook 8.5 mm) | hooks 10 mm: 1.4 % |
| fit (board vs lid) | the lid's lip and hooks touched the header: 130 mm3 | lip removed; hooks moved out of the way with extra room inside the end walls |
| negative controls | a shifted board and a stubby hook are both flagged | (kept as permanent checks) |

## Gaps in Fit2Print this sample exposed
1. **No bridge-versus-cantilever in the geometric check.** It said "starts in mid-air" for every roof of a slot. FIXED: `airscan.py` shared by the toolpath and geometric checks, with tests.
2. **The assembly and fit checks are hard-wired to the radio.** The sample needed its own `run_checks.py`. Needed: a project file that declares the parts, the build order and the screws, and generic checks that read it.
3. **No plate/slicing step outside Phonosphere.** `make_plate` is still in the radio's repo, so the sample's toolpath check could not be run on a sliced plate. Needed: extract `plate.py` (next).
4. **The dashboard has only a Phonosphere adapter.** The sample has no print log yet; needs a generic record format.
5. **The snap-fit strain limit is a guess** (2 %), to be calibrated with a printed hook coupon.
6. **Parameters are read from the model by a regular expression**, which is fragile. Needed: the model exports its parameters (OpenSCAD can echo them) into a file the checks read.

## Not yet done for this sample
Slicing and the toolpath check on the plates; a hook coupon; the print, the photo and the log; verifying the board's dimensions with callipers.
