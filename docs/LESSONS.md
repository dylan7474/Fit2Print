# Lessons: each real failure and the check it became

(From Phonosphere, 2026-10-16 onwards. The check column says where it lives or will live.)

| Failure | What it cost | Check |
|---|---|---|
| A line over air judged by length, not by what held it up: a groove broke out of a corner | a print | toolpath check: cantilever depth and sides held, not line length |
| Arches printed on an unsupported lap shelf | a failed print | unsupported-plastic check; never print a flagged plate without looking |
| Supports filled blind pilots and small holes | a failed print | as-built check: supports inside small holes |
| Seam bolts unreachable with a driver (hand tried it: an hour for 4 bolts) | a redesign | fixings check: a 6 mm rod, 100 mm long, straight from outside to the head |
| Bolt holes passing through air, not plastic | a redesign | fixings check: plastic around each hole |
| The file named on the command line was a stale STL from an older design | three "checks" of the wrong part | refuse any STL older than the model; rebuild or stop |
| The as-built check tried only 0/90/180/270 turns; the slicer had turned the plate 45 degrees | false "missing" and "extra" | find the turn angle by chamfer distance |
| A pod lid collided with turned lugs | a part that would not fit | fit check: part against part |
| A lug's wedge was cut short by the pod, leaving a flat 4 mm shelf: ragged print | a coupon | layer slicer: z-step in area; fix by flush lug and 45 degree underside |
| A screw foot with a flat 4 mm underside, spotted by hand in the slicer | a check that missed it | wedge under every protruding boss; the checker now needs a case for it |
| The pod cannot be pushed in or out through the open back (six lugs in the way) | would have been found at assembly | assembly sweeps, in the real order |
| A check test that models the wrong gap (the plates lock a 1.5 mm gap) | a false alarm | model the gaps the real build has |
| `pgrep -f` matches its own command line: false "still running" | hours of stuck waits | wait on a PID with `kill -0` |
| A tool printed a secret into the log while looking something up | a credential exposed | print only the fields you mean; mask by default |
| A fix was "done" on paper (cone-tipped holes, painted supports) but no real print had tried it, and the user rightly asked for a test | a doubt that stayed open for four days | **coupon**: cut the doubtful spots from the part's own STL and print them together (`fit2print coupon`); call a fix "checked", not "proven", until a print shows it |
| The first coupon covered one spot; the real failure had several (shelf, tab, two kinds of blind hole) | a second round of planning | one plate of several coupons, one from each way the part can go wrong, all with the part's own slicer settings |
| A check that passes proves nothing until it is seen to fail; the known-bad plate used as the control was a whole part and timed out at 250 s | a control that never finished | known-bad fixtures must be **small coupons** (a 56 mm region slices and checks in 20 s): the old flat-pilot end with auto supports gives BLOCK, the new end passes |
| The geometry cure (a 45 degree drill-point tip) held even under auto supports; the settings cure (painted supports only) is a second layer | confidence | test both: the fix must pass with the setting that once broke it, so it does not depend on one setting staying right |
| "I can't see how it connects": blind screw holes and screws from the inside show nothing from the front | an afternoon of doubt | a pulled-apart picture from the real model (shell, lugs, screws, face); say which printed pieces have a counterpart yet (the sunburst bolts to shell_upper, which is not printed) |
| Test prints made before a design change look right but have fixings in the old places | wrong conclusions from a hand fit | every printed piece records the design hash it was made from (PLATE_RESULTS `design_sha`); warn when a design change moved a fixing |
| Which way up a part prints decides what is an overhang: tabs on the bed are free, the recess a tab sits in is a shelf in the air | confusion over "tab up / tab down" | say the print orientation and name each overhang (which seam, how wide, how high) in every report |
| "Cut where the outline is shortest" steered a cut into the LED window: a window shortens the outline | a cut through the display | cut choice is by section topology (separate pieces and holes), then local change, then nearness to an even split; negative control with a real window |
| A relative output folder: OpenSCAD runs elsewhere, found no part, and every section looked "empty" (100% of the volume lost) | a silent wrong answer | all paths absolute; a real OpenSCAD complaint is a failure, only a plain "empty" is a gap; the volume check (sections + pin holes = the part) caught it |
| A screw hole's counterbore cut through the back plate's lip ring: the exported STL was not watertight | a model flaw found only by a warning | check that a screw's hole passes only through the part it belongs to (to do) |
| A model drawn in print orientation (face on the bed) gives upside-down pictures with `view = "bottom"` | a confusing render | say so in the render help; use `angle = [180, 0, 180]` for the bed side |
| `plate` slices one STL at a time, so eight sections meant eight commands | friction | `plate --split NAME` for all sections (to do) |

