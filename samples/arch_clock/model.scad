part = "assembly";    // "assembly" | "exploded" | "front" | "back" | "retainer" | "front_full" (the front before it is cut into sections)
// Arch wall clock (SAMPLE): proof-of-concept model for Fit2Print. Units mm. Every dimension is a parameter. UNVERIFIED = a guess to check.
include <hardware.scad>
$fn = 96;

// ---- the arch (x across, y up the wall, z out of the wall; the FRONT face is z = 0 and lies on the bed)
W = 330;  Hr = 190;                    // width; height of the straight part under the arch (the arch's radius is W/2)
plate = 10;  wall = 6.5;  depth = 40;  // front plate; side wall (thick on purpose: pins need >= 5.7 mm); total depth of the front part
back_t = 6;  lip = 3;  lip_h = 0;  lip_clr = 0.4;     // lip_h = 0: no lip. A lip ring ran through the screw bosses (the counterbores cut it): found by the export's not-watertight warning, 2026-11-01

// ---- the display module (library: max7219-8x32-matrix; sizes third-party, UNVERIFIED)
mod = [128, 32];  mod_lift = 2.0;      // the board's size; how far behind the plate's back face it sits
win = [122, 28];                       // the opening: 3 mm of lip all round
pocket = [129.6, 33.6];  pocket_d = 4; // the rebate behind the lip that the board sits in
win_y = Hr + 20;                       // the window's centre height on the wall
ret_screw_dx = 70;                     // the two retainer screws, either side of the module

// ---- the ESP32 (library: esp32-devkitc-v4)
esp = [54.4, 27.9];
usb_slot = [14, 8];

// ---- fixings
boss_d = 11;  pilot_d = 2.5;  pilot_h = 14;  clear_d = 3.4;
key_dx = 60;  key_head = 9;  key_slot = 4.2;     // keyholes 120 mm apart

module arch2d(w = W, hr = Hr) union() {
    translate([-w / 2, 0]) square([w, hr]);
    translate([0, hr]) intersection() { circle(r = w / 2, $fn = 180); translate([-w / 2, 0]) square([w, w / 2]); }
}
module outline(inset = 0) offset(delta = -inset) arch2d();

// screw bosses stand against the wall: round the arch (angles) and down the sides (heights)
rc = W / 2 - wall - boss_d / 2 + 0.5;
boss_pts = concat([for (y = [30, 150]) for (s = [-1, 1]) [s * rc, y]], [for (a = [48, 132]) [rc * cos(a), Hr + rc * sin(a)]]);

module front() difference() {
    union() {
        linear_extrude(plate) outline();
        translate([0, 0, plate - 0.01]) linear_extrude(depth - plate + 0.01) difference() { outline(); outline(wall); }
        for (p = boss_pts) translate([p[0], p[1], plate - 0.01]) cylinder(d = boss_d, h = depth - plate + 0.01);
        // the lip's posts for the retainer: two bosses beside the pocket
        for (s = [-1, 1]) translate([s * ret_screw_dx, win_y, plate - 0.01]) cylinder(d = 8, h = 6);
    }
    // the window through the plate, and the rebate behind it for the board
    translate([-win[0] / 2, win_y - win[1] / 2, -1]) cube([win[0], win[1], plate + 2]);
    translate([-pocket[0] / 2, win_y - pocket[1] / 2, plate - pocket_d]) cube([pocket[0], pocket[1], pocket_d + 0.02]);
    for (s = [-1, 1]) translate([s * ret_screw_dx, win_y, plate - 0.5]) cylinder(d = pilot_d, h = 8);
    // three engraved rings round the front (grooves 1.2 deep, 3 wide) at 16, 26 and 36 mm in from the edge
    for (r = [16, 26, 36]) translate([0, 0, -0.01]) linear_extrude(1.2) difference() { outline(r); outline(r + 3); }
    // the six pilots for the back plate's screws
    for (p = boss_pts) translate([p[0], p[1], depth - pilot_h]) cylinder(d = pilot_d, h = pilot_h + 0.01);
}

module back() difference() {
    union() {
        linear_extrude(back_t) outline();
        // a lip that drops inside the front's wall to line the two up
        if (lip_h > 0) translate([0, 0, back_t - 0.01]) linear_extrude(lip_h) difference() { outline(wall + lip_clr); outline(wall + lip_clr + lip); }
    }
    for (p = boss_pts) translate([p[0], p[1], -1]) cylinder(d = clear_d, h = back_t + lip_h + 2);
    for (p = boss_pts) translate([p[0], p[1], back_t - 2.4]) cylinder(d = 6.4, h = lip_h + 4);        // heads sit in counterbores
    // two keyholes to hang it (120 mm apart): a round head, then a slot going up
    for (s = [-1, 1]) translate([s * key_dx, Hr * 0.8, -1]) hull() { cylinder(d = key_head, h = back_t + 2); translate([0, 14, 0]) cylinder(d = key_slot, h = back_t + 2); }
    // the cable slot for the ESP32's USB, at the bottom edge
    translate([-usb_slot[0] / 2, -1, -1]) cube([usb_slot[0], wall + 1.5, back_t + lip_h + 2]);
    // a shallow pocket on the inside for the ESP32 (it is held by a cable tie through two slots)
    translate([-esp[0] / 2, 40, back_t - 1.6]) cube([esp[0], esp[1], 2]);
    for (s = [-1, 1]) translate([s * (esp[0] / 2 + 3), 40 + esp[1] / 2 - 4, -1]) cube([2.2, 8, back_t + 2]);
}

module retainer() difference() {
    linear_extrude(3) offset(r = 3) square([mod[0] + 2 * 6 - 6, mod[1] + 2 * 4 - 6], center = true);
    translate([-(win[0] - 8) / 2, -(win[1] - 8) / 2, -1]) cube([win[0] - 8, win[1] - 8, 5]);
    for (s = [-1, 1]) translate([s * ret_screw_dx, 0, -1]) cylinder(d = clear_d, h = 5);
}

module boards() {
    translate([-mod[0] / 2, win_y - mod[1] / 2, plate - pocket_d + 0.01]) max7219_8x32_matrix_shape();
    translate([-esp[0] / 2, 40, 0]) esp32_devkitc_v4_shape();
}

module placed_back() translate([0, 0, depth + 0.2]) mirror([0, 0, 0]) back();
if (part == "front" || part == "front_full") front();
if (part == "back") back();
if (part == "retainer") retainer();
if (part == "assembly") { color("#8a6a4a") front(); color("#6f553b") placed_back(); color("#555") translate([0, 0, plate - 0.01]) retainer(); }
if (part == "exploded") { color("#8a6a4a") front(); color("#6f553b") translate([0, 0, depth + 60]) back(); color("#555") translate([0, 0, plate + 25]) retainer(); }
