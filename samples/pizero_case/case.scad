// Pi Zero 2 W wall case: proof-of-concept model (Fit2Print example project). Units mm. Every dimension is a parameter.
// part = "assembly" | "exploded" | "base" | "lid" | "board"      (the case's lower-left corner is the origin; x along the long axis; z up)
part = "exploded";
$fn = 48;

// ---- the board (standard Pi Zero drawing: VERIFY on the real board)
pcb = [65, 30, 1.4];  hole_d = 2.75;  hole_in = 3.5;  corner_r = 3;
header_h = 9;  tails = 2;

// ---- snap fit: four hooks on the lid catch in four windows in the two END walls (the long walls have the ports and the header)
hook_w = 6; hook_t = 1.2; hook_len = 10; tooth = 0.7; win_h = 2.0; hook_room = hook_t + 0.5;

// ---- the case
wall = 2.0;  floor_t = 4.0;  lid_t = 2.0;  clr = 0.4;
post_h = tails + 1.0;  post_d = 5.5;  pin_d = hole_d - 0.35;
inner = [pcb[0] + 2 * clr + 2 * hook_room, pcb[1] + 2 * clr];
inner_h = post_h + pcb[2] + header_h + 0.8;
outer = [inner[0] + 2 * wall, inner[1] + 2 * wall, floor_t + inner_h];
bx = wall + clr + hook_room;  by = wall + clr;  bz = floor_t + post_h;          // the board's origin in the case's frame

// ---- openings, along the board's near long edge (y = 0), from its left end
usb_w = 8.4; usb_h = 3.4; hdmi_w = 11.8; hdmi_h = 3.8;
port_x = [12.4, 41.4, 54.0];                  // mini HDMI, micro USB (data), micro USB (power)
sd = [12.0, 2.6];
// ---- hanging: two keyholes through the floor, head recess on the back
key_head = 7.8; key_slot = 3.8; key_spacing = 40; key_len = 6; key_rec = 2.4;

module rrect_c(s, r) translate([s[0] / 2, s[1] / 2]) offset(r = r) square([s[0] - 2 * r, s[1] - 2 * r], center = true);
module board() {
    color("#1a7f37") linear_extrude(pcb[2]) difference() {
        rrect_c([pcb[0], pcb[1]], corner_r);
        for (x = [hole_in, pcb[0] - hole_in], y = [hole_in, pcb[1] - hole_in]) translate([x, y]) circle(d = hole_d);
    }
    color("#222") translate([7.1, pcb[1] - 5.1, pcb[2]]) cube([51, 5, header_h]);                 // the pins
    color("#999") translate([port_x[0] - 5.6, -1, pcb[2]]) cube([11.2, 7.5, 3.2]);                // mini HDMI
    for (i = [1, 2]) color("#aaa") translate([port_x[i] - 3.7, -1.2, pcb[2]]) cube([7.4, 5.6, 2.6]);   // micro USB x2
    color("#bbb") translate([-1.5, pcb[1] / 2 - 6, pcb[2]]) cube([13, 12, 1.5]);                   // SD slot
    color("#ccc") translate([32, 8, pcb[2]]) cube([14, 12, 1.5]);                                  // radio shield
}
module posts() for (x = [hole_in, pcb[0] - hole_in], y = [hole_in, pcb[1] - hole_in]) translate([bx + x, by + y, floor_t - 0.01]) {
    cylinder(d = post_d, h = post_h + 0.01);
    cylinder(d = pin_d, h = post_h + pcb[2] + 0.6);
}
module keyholes() for (s = [-1, 1]) translate([outer[0] / 2 + s * key_spacing / 2 - key_len / 2, outer[1] / 2, 0]) {
    translate([0, 0, -0.1]) cylinder(d = key_head, h = key_rec + 0.1);                                   // head recess (the screw head sits here)
    hull() for (dx = [0, key_len]) translate([dx, 0, -0.1]) cylinder(d = key_slot, h = floor_t + 0.2);   // the narrow slot, through
    hull() for (dx = [0, key_len]) translate([dx, 0, -0.1]) cylinder(d = key_head, h = key_rec + 0.1);   // the recess runs the slot's length
}
module base() color("#2b2b2b") difference() {
    union() { translate([0, 0, 0]) linear_extrude(outer[2]) rrect_c([outer[0], outer[1]], 3); posts_solid(); }
    translate([wall, wall, floor_t]) linear_extrude(outer[2]) rrect_c(inner, 1.5);                       // the cavity
    for (i = [0, 1, 2]) translate([bx + port_x[i] - (i == 0 ? hdmi_w : usb_w) / 2, -1, bz + pcb[2] - 0.2]) cube([i == 0 ? hdmi_w : usb_w, wall + 2, (i == 0 ? hdmi_h : usb_h) + 0.4]);
    translate([-1, by + pcb[1] / 2 - sd[0] / 2, bz + pcb[2] - 0.2]) cube([wall + 2, sd[0], sd[1] + 0.4]);   // SD slot
    for (xs = [-0.1, outer[0] - wall - 0.1], y = [outer[1] * 0.2, outer[1] * 0.8]) translate([xs, y - hook_w / 2 - 0.2, outer[2] - hook_len - 0.2]) cube([wall + 0.2, hook_w + 0.4, win_h + 0.4]);   // snap windows
    keyholes();
}
module posts_solid() for (x = [hole_in, pcb[0] - hole_in], y = [hole_in, pcb[1] - hole_in]) translate([bx + x, by + y, floor_t - 0.01]) {
    cylinder(d = post_d, h = post_h + 0.01); cylinder(d = pin_d, h = post_h + pcb[2] + 0.6);
}
module lid() color("#c9a227") difference() {
    union() {
        linear_extrude(lid_t) rrect_c([outer[0], outer[1]], 3);
        for (side = [0, 1], y = [outer[1] * 0.2, outer[1] * 0.8]) {          // hooks hang inside the end walls, the tooth pointing out into the window
            sgn = side == 0 ? -1 : 1;
            x0 = side == 0 ? wall + 0.2 : outer[0] - wall - 0.2 - hook_t;
            xf = side == 0 ? x0 : x0 + hook_t;                                // the hook's outer face
            translate([x0, y - hook_w / 2, -hook_len]) cube([hook_t, hook_w, hook_len + 0.01]);
            // the tooth: a flat catch face on the plate side (holds the lid on), a 45-degree lead-in on the tip side (slides in)
            translate([xf, y + hook_w / 2, -hook_len]) rotate([90, 0, 0]) linear_extrude(hook_w) polygon([[0, 0.3], [sgn * tooth, 0.3 + tooth], [sgn * tooth, 0.3 + tooth + 1.0], [0, 0.3 + tooth + 1.0 + 0]]);
        }
    }
    for (i = [0 : 4]) translate([outer[0] / 2 - 8 + i * 4 - 0.8, outer[1] / 2 - 6, -0.1]) cube([1.6, 12, lid_t + 0.2]);   // vent slots
}
module board_in_case() translate([bx, by, bz]) board();
module lid_on() translate([0, 0, outer[2]]) lid();
if (part == "base") base();
if (part == "lid") lid();
if (part == "lid_print") translate([0, outer[1], lid_t]) rotate([180, 0, 0]) lid();      // flat on the bed, hooks up
if (part == "board") board();
if (part == "assembly") { base(); board_in_case(); lid_on(); }
if (part == "exploded") { base(); translate([0, 0, 24]) board_in_case(); translate([0, 0, 52]) lid_on(); }

// ---- check cases for run_checks.py (kept in the model so the checks use the model's own geometry)
chk_off = 0;
if (part == "chk_board_base") intersection() { base(); board_in_case(); }
if (part == "chk_board_lid") intersection() { lid_on(); board_in_case(); }
if (part == "chk_lid_base") intersection() { base(); lid_on(); }
if (part == "chk_lid_path") intersection() { base(); translate([0, 0, chk_off]) lid_on(); }
if (part == "chk_board_base_shifted") intersection() { base(); translate([0, 1.0, 0]) board_in_case(); }
