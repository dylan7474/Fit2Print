# What the arch clock sample found (2026-11-01)

Built to test the new section splitter end to end (idea, model, export, cut, check, slice). Everything below was a real fault found by doing it, and each is now a test or a lesson in Fit2Print.

| Found | Where | What was done |
|---|---|---|
| A relative `--out` folder: OpenSCAD runs in another folder, so it found no part and every section came out "empty": 100% of the volume "lost" | `split.py` | all paths made absolute; test `test_a_relative_output_folder_works` |
| A missing-file warning from OpenSCAD looked like an empty gap and was silently skipped | `split.py` | a real complaint is a failure, a plain "empty" is a gap; negative control `test_a_part_openscad_cannot_read...` |
| "Cut where the outline is shortest" steered cuts INTO the LED window (a window shortens the outline) | `split.py` best_cut | cut choice is now: fewest pieces/holes in the section, then least change within 3 mm, then nearest the even split; test with a window |
| Cuts were limited to +-15% of the even split, so a cut could not dodge a 122 mm window | `split.py` | cuts may move up to half a piece while every piece still fits the bed |
| One pin per 45 mm2 of section gave only 2 pins on a 355 mm seam | `split.py` | a pin every 45 mm along the seam (Phonosphere: 7 on 360 mm) |
| Two splits into one folder overwrote each other's record | `split.py` | the record is `NAME_split.json` |
| The model's back plate had a lip ring that the screw counterbores cut through: the exported STL was **not watertight** | `model.scad` | found by the export warning; lip removed. A check "screw hole passes through another feature" would have caught it earlier (to do) |
| `view = "bottom"` shows the part upside down (y flipped) | renders | the model is drawn in print orientation (front face on the bed), so the front picture uses `angle = [180, 0, 180]`; worth a note in the render help |
| `plate` takes one STL at a time | cli | looped by hand over the eight sections; a `plate --split NAME` would slice them all (to do) |

## What the sample proves
* A 330 x 355 x 40 mm front and a 330 x 355 x 6 mm back, both too big for the 256 mm bed, are cut into four sections each that all fit; every section lies on a flat cut or original face; the sections plus the pin holes equal the part's volume.
* Every section passes the overhang check and slices on the real Bambu Studio profile (front_s01..04: 99, 212, 68 and 180 min; back_s01..04: 93, 94, 75 and 75 min).
* A 0.4 scale test needs no cuts at all.

## What it does NOT prove
* Nothing was printed. Pins, glue and the dry fit of the sections are untested on a real printer.
* The pin hole depth (8 mm, 3.3 mm hole for a 3.0 mm pin) is Phonosphere's, proven on its back seams, not re-proven here.
* The cuts only go through thick walls (6.5 mm). Thin-walled parts get a warning and no pins (a lap or screws would be needed: not built).
