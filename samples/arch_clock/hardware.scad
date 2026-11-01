// hardware.scad: WRITTEN BY Fit2Print from the component library, again every time the pictures or the 3D view are drawn. DO NOT EDIT: change the
// library (measure a size) instead. Use it with  include <hardware.scad>  and draw a real part with  <id with _ for ->_shape();  e.g. esp32_devkitc_v4_shape();
// Every part is in its own frame (see its note); translate and rotate it where the design needs it. Never draw a library part as a plain box.

// ---- 8x32 dot-matrix LED module, 4-in-1 MAX7219 type (Youmile TS-YM-322 blue)  (library id: max7219-8x32-matrix)
// Outline only: the board and overall height are seller figures, the LED blocks and header are estimates, and the corner holes are placed by guess. Everything is unverified until you measure the real module.
max7219_8x32_matrix_pcb_length = 128.0;   // mm, UNVERIFIED (third-party)
max7219_8x32_matrix_pcb_width = 32.0;   // mm, UNVERIFIED (third-party)
max7219_8x32_matrix_pcb_thickness = 1.6;   // mm, UNVERIFIED (estimate)
max7219_8x32_matrix_overall_height = 14.0;   // mm, UNVERIFIED (third-party)
max7219_8x32_matrix_matrix_height = 8.0;   // mm, UNVERIFIED (estimate)
max7219_8x32_matrix_hole_d = 3.2;   // mm, UNVERIFIED (estimate)
max7219_8x32_matrix_hole_inset_x = 3.0;   // mm, UNVERIFIED (estimate)
max7219_8x32_matrix_hole_inset_y = 3.0;   // mm, UNVERIFIED (estimate)
max7219_8x32_matrix_connector_height = 8.5;   // mm, UNVERIFIED (estimate)
module max7219_8x32_matrix_pcb() color("#0B3C8C") { difference() { translate([0.0000,0.0000,0.0000]) cube([128.0000,32.0000,1.6000]); translate([3.0000,3.0000,-1.0000]) cylinder(d=3.2000,h=3.6000,$fn=32); translate([125.0000,3.0000,-1.0000]) cylinder(d=3.2000,h=3.6000,$fn=32); translate([3.0000,29.0000,-1.0000]) cylinder(d=3.2000,h=3.6000,$fn=32); translate([125.0000,29.0000,-1.0000]) cylinder(d=3.2000,h=3.6000,$fn=32); } }   // Board [unverified]
module max7219_8x32_matrix_matrix_1() color("#1A1A1A") { translate([0.0000,0.0000,1.6000]) cube([32.0000,32.0000,8.0000]); }   // LED block 1 [unverified]
module max7219_8x32_matrix_matrix_2() color("#1A1A1A") { translate([32.0000,0.0000,1.6000]) cube([32.0000,32.0000,8.0000]); }   // LED block 2 [unverified]
module max7219_8x32_matrix_matrix_3() color("#1A1A1A") { translate([64.0000,0.0000,1.6000]) cube([32.0000,32.0000,8.0000]); }   // LED block 3 [unverified]
module max7219_8x32_matrix_matrix_4() color("#1A1A1A") { translate([96.0000,0.0000,1.6000]) cube([32.0000,32.0000,8.0000]); }   // LED block 4 [unverified]
module max7219_8x32_matrix_connector() color("#222222") { translate([1.0000,9.6000,1.6000]) cube([2.5400,12.7000,8.5000]); }   // 5-pin header (one end) [unverified]
module max7219_8x32_matrix_shape() { max7219_8x32_matrix_pcb(); max7219_8x32_matrix_matrix_1(); max7219_8x32_matrix_matrix_2(); max7219_8x32_matrix_matrix_3(); max7219_8x32_matrix_matrix_4(); max7219_8x32_matrix_connector(); }

// ---- Espressif ESP32-DevKitC V4 (ESP32-WROOM-32)  (library id: esp32-devkitc-v4)
// Outline only: the board and the overall length are Espressif's figures; the connector, header and module sizes are estimates (marked unverified) until you measure the real board.
esp32_devkitc_v4_pcb_length = 48.2;   // mm, UNVERIFIED (official)
esp32_devkitc_v4_pcb_width = 27.9;   // mm, UNVERIFIED (official)
esp32_devkitc_v4_total_length = 54.4;   // mm, UNVERIFIED (official)
esp32_devkitc_v4_row_spacing = 25.4;   // mm, UNVERIFIED (derived)
esp32_devkitc_v4_pcb_thickness = 1.6;   // mm, UNVERIFIED (estimate)
esp32_devkitc_v4_header_length = 48.26;   // mm, UNVERIFIED (derived)
esp32_devkitc_v4_header_housing_h = 2.5;   // mm, UNVERIFIED (estimate)
esp32_devkitc_v4_pins_below = 6.0;   // mm, UNVERIFIED (estimate)
esp32_devkitc_v4_module_length = 25.5;   // mm, UNVERIFIED (estimate)
esp32_devkitc_v4_module_width = 18.0;   // mm, UNVERIFIED (estimate)
esp32_devkitc_v4_module_height = 3.1;   // mm, UNVERIFIED (estimate)
esp32_devkitc_v4_usb_width = 7.5;   // mm, UNVERIFIED (estimate)
esp32_devkitc_v4_usb_depth = 5.6;   // mm, UNVERIFIED (estimate)
esp32_devkitc_v4_usb_height = 2.8;   // mm, UNVERIFIED (estimate)
esp32_devkitc_v4_usb_overhang = 1.0;   // mm, UNVERIFIED (estimate)
module esp32_devkitc_v4_pcb() color("#1B5E20") { translate([0.0000,0.0000,0.0000]) cube([48.2000,27.9000,1.6000]); }   // Board [unverified]
module esp32_devkitc_v4_module() color("#1F1F1F") { translate([28.9000,4.9500,1.6000]) cube([25.5000,18.0000,3.1000]); }   // ESP32 module (antenna end) [unverified]
module esp32_devkitc_v4_usb() color("#B8B8B8") { translate([-1.0000,10.2000,1.6000]) cube([5.6000,7.5000,2.8000]); }   // Micro USB socket [unverified]
module esp32_devkitc_v4_header_a() color("#222222") { translate([0.0000,-0.0200,1.6000]) cube([48.2600,2.5400,2.5000]); }   // Pin row (long edge) [unverified]
module esp32_devkitc_v4_header_b() color("#222222") { translate([0.0000,25.3800,1.6000]) cube([48.2600,2.5400,2.5000]); }   // Pin row (other edge) [unverified]
module esp32_devkitc_v4_pins_a() color("#B08D57") { translate([0.0000,0.7500,-6.0000]) cube([48.2600,1.0000,6.0000]); }   // Pins below (row 1) [unverified]
module esp32_devkitc_v4_pins_b() color("#B08D57") { translate([0.0000,26.1500,-6.0000]) cube([48.2600,1.0000,6.0000]); }   // Pins below (row 2) [unverified]
module esp32_devkitc_v4_shape() { esp32_devkitc_v4_pcb(); esp32_devkitc_v4_module(); esp32_devkitc_v4_usb(); esp32_devkitc_v4_header_a(); esp32_devkitc_v4_header_b(); esp32_devkitc_v4_pins_a(); esp32_devkitc_v4_pins_b(); }
