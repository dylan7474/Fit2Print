// calibration_card.scad -- one plate, ~35 min at 0.28 mm: measure it once per filament + profile, then run calibrate.py.
// It replaces the one-off ladders (knob bores, pin holes, posts, bridges) with a single standard test.
//   A  hole ladder     holes drawn 2.5 ... 9.6: measure what they print (calipers, inside jaws, or the drill bit that just fits)
//   B  outside blocks  20 and 40 mm: measure what they print
//   C  pins            four 3.0 x 15 pins, printed standing: push one into the 3.3 hole in A
//   D  thin walls      0.8 ... 2.4 mm: which stand and are solid
//   E  bridges         spans 4 ... 15 mm, 2 mm thick: which sag (lay a straight edge on them)
//   F  shelves         cantilevers 2 ... 11 mm off a post, 2 mm thick: which print clean (this calibrates gate.py's overhang rules)
//   G  leaning walls   2.4 mm walls leaning 30 ... 75 degrees from vertical, 10 mm tall: the steepest slope whose underside stays clean
$fn = 48;
holes = [2.5, 3.0, 3.3, 4.2, 5.0, 6.0, 9.6];

// A: hole ladder, 4 mm thick
translate([0, 0, 0]) difference() {
    cube([100, 20, 4]);
    for (i = [0 : len(holes) - 1]) translate([8 + i * 14, 10, -1]) cylinder(d = holes[i], h = 6);
    for (i = [0 : len(holes) - 1]) translate([8 + i * 14, 17, 3.2]) linear_extrude(1) text(str(holes[i]), size = 2.4, halign = "center", valign = "center");
}
// B: outside blocks
translate([0, 28, 0]) cube([20, 20, 6]);
translate([30, 28, 0]) cube([40, 20, 6]);
// C: pins, standing
for (i = [0 : 3]) translate([82 + i * 6, 38, 0]) cylinder(d = 3.0, h = 15);
// D: thin walls on a 2 mm base
translate([0, 56, 0]) {
    cube([60, 22, 2]);
    for (i = [0 : 4]) translate([4 + i * 11, 2, 2]) cube([[0.8, 1.2, 1.6, 2.0, 2.4][i], 18, 10]);
}
// E: bridges (two 6 x 6 x 8 pillars, a 2 mm plate across)
spans = [4, 6, 8, 10, 12, 15];
for (i = [0 : 5]) translate([0 + (i % 3) * 36, 84 + floor(i / 3) * 14, 0]) {
    translate([0, 0, 0]) cube([6, 10, 8]);
    translate([6 + spans[i], 0, 0]) cube([6, 10, 8]);
    translate([0, 0, 8]) cube([12 + spans[i], 10, 2]);
}
// F: shelves (a post with a cantilever near the top)
shelves = [2, 3.5, 5, 8, 11];
for (i = [0 : len(shelves) - 1]) translate([0 + i * 26, 112, 0]) {
    cube([6, 10, 12]);
    translate([6, 0, 8]) cube([shelves[i], 10, 2]);
}
// G: leaning walls (angle from vertical; each is 10 mm tall and leans toward +x, a 45 degree wall climbs 10 mm over 10 mm)
leans = [30, 45, 55, 65, 75];
for (i = [0 : len(leans) - 1]) translate([0, 130 + i * 14, 0])
    multmatrix([[1, 0, tan(leans[i]), 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) cube([2.4, 10, 10]);
