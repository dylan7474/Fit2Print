# Arch wall clock (SAMPLE)

A sample project used to test Fit2Print, and in particular its **section splitter** (`fit2print split`). It is a 330 x 355 x 40 mm arch-shaped wall clock, deliberately **bigger than the print bed**, so the front and the back can only be printed in sections.

* `brief.md`: stage 1. Every answer was made up (Claude was told to answer the questions itself); sizes come from the component library.
* `model.scad`: the parametric model (front, back, retainer) with real library shapes for the LED module and the ESP32.
* `stl/`: `front_full`, `back_full` (too big for the bed) and `retainer`.
* `sections/`: what `fit2print split` made: four front sections, four back sections, the loose pins for each, a picture of the cuts, and a record (`*_split.json`).
* `plates/`: the sliced print files, one per section.
* `assembly.toml`: how the sections go together.
* `FINDINGS.md`: the faults this sample found in Fit2Print and in its own model.

Regenerate everything:

    fit2print render .          # pictures and the 3D view
    fit2print export .          # stl/
    fit2print split stl/front_full.stl --out sections --base front
    fit2print split stl/back_full.stl  --out sections --base back
    fit2print plate sections/front_s01.stl --project . --out plates     # and the others

Try it small first: `fit2print split stl/front_full.stl --out test --base front --scale 0.4` is one piece on the bed, no cuts, no pins.
