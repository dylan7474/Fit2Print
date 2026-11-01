# Brief: Sample: Arch wall clock

*(A SAMPLE used to test Fit2Print, especially its section splitter. Every answer below was made up by Claude on the owner's instruction "answer all the questions using your imagination", with real sizes taken from the component library. None of it is a real person's wish.)*

## What it is for
A big art-deco style wall clock for a hallway: a tall arch with three engraved rings round the front and a small glowing LED window in the middle that shows the time. It is deliberately LARGER THAN THE PRINT BED (330 x 355 mm), so it can only be printed in sections: it is the test piece for cutting a big design into pieces that fit.

## The hardware it holds or touches (measured values only; mark the rest UNVERIFIED)
* One 8 x 32 MAX7219 LED matrix module (4-in-1): 128 x 32 mm board, LEDs 8 mm high. Library entry `max7219-8x32-matrix` (third-party sizes: UNVERIFIED until measured).
* One ESP32-DevKitC V4 board, 54.4 x 27.9 mm. Library entry `esp32-devkitc-v4` (from the official drawing).
* Wall hanging: two keyhole slots in the back plate, 120 mm apart (UNVERIFIED: depends on the screws in the wall).

## Printer and material
Profile: bambu_a1_pla (256 x 256 x 256 mm bed). PLA, any dark colour; the ring grooves look best in a contrasting second colour later (not needed now).

## Must
1. Overall size about 330 wide x 355 tall x 46 deep: bigger than the bed, so it must be split.
2. The LED window shows the whole module through a 122 x 28 mm opening; the module sits behind a 2 mm lip, held in by a printed retainer and two M3 screws.
3. The back plate screws on with six M3 self-tapping screws from behind into bosses inside the wall.
4. A USB cable for the ESP32 leaves through a slot in the bottom of the back plate.
5. Printable on the A1 with no supports under the big flat faces; sections join with loose pins.

## Nice to have
* A second colour in the three ring grooves.
* A little spirit level built into the top (not in this sample).

## Decisions made
* One display module (not two): the clock shows HH:MM and the date scrolling.
* Walls 6.5 mm thick on purpose: thick enough for 3 mm joint pins, and stiff when the case is cut into sections.
* Grooves, not raised rings, on the front, so the front face prints flat on the bed.

## Assumptions the AI made (the person should correct these)
* The module sizes come from seller listings, not a drawing (UNVERIFIED).
* The ESP32 sits in a pocket on the back plate and is held by a tie, not screws (the DevKit has no mounting holes).

## Open questions
* Which colour? (not blocking)
