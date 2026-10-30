# Brief: Raspberry Pi Zero 2 W wall case

*Stage 1 of the Fit2Print workflow. Written 2026-10-30 from the user's answers. This is the second test project (the first was the Phonosphere radio): its job is to show which stages and checks generalise.*

## What it is for
A case for a Raspberry Pi Zero 2 W that **hangs on a wall or under a desk** (keyhole slots, no tools to remove it), with a **snap-fit lid** (no screws).

## The board (from the standard Pi Zero mechanical drawing: VERIFY against the real board with callipers before printing)
* 65 x 30 mm, 1.4 mm thick, 3 mm corner radius. Four mounting holes 2.75 mm, centred 3.5 mm in from each edge (58 x 23 mm apart).
* **Header fitted** (40-pin, soldered): the pins stand about 9 mm above the board and the tails stick about 2 mm out underneath.
* Along one long edge: mini-HDMI, micro-USB (data), micro-USB (power). One short end: microSD slot. The other short end: camera connector. The other long edge: the header.
* Tallest parts on top: the header, the mini-HDMI (about 3.2 mm), the metal radio shield (about 1.5 mm).

## Printer and material
Bambu A1, 0.4 mm nozzle, 0.28 mm layers (Extra Draft), PLA, profile `profiles/bambu_a1_pla.toml`.

## Must
1. Hold the board on four posts so it cannot rattle, with room underneath for the header's pin tails.
2. Openings for the three ports and the SD slot (and the camera connector, closed off with a removable plug or left open: to be decided).
3. Hang from two keyhole slots on a wall screw (M3.5 to M4 head), and sit flat against the wall.
4. A lid that snaps on by hand and comes off again with a fingernail or a coin, and survives opening at least 20 times.
5. Print with no supports, in as few parts as possible (the base and the lid), each flat on the bed.
6. A little ventilation (slots over the CPU).

## Nice to have
* The header kept reachable: a removable section of the lid over the GPIO pins.
* A label recess.

## Decisions (2026-10-30)
* Direction approved by the user from concept picture 01: a plain box, the board filling it, a flat lid with hooks.
* **Assumed, not asked** (the user said "go ahead"): GPIO stays inside, closed; the camera end is closed; black base, a contrasting lid (colour is only a render colour for now). Change these if wrong.
* Board dimensions still unverified against the real board.

## Checks this project will exercise
fit (board against case), printability (overhangs on the snap hooks and keyholes), snap-fit strength and tolerance (a coupon), assembly order, the screw-reach rule for the wall screws, the print log and the dashboard.
