// OBS VCR Remote — ESP32 enclosure
// 
// Hardware:
//   * ESP32 DOIT DevKit v1 (~54.4 x 28.3 mm)
//   * 5mm IR LED through the front wall
//   * TO-92 NPN transistor inside, held by its own leads
//   * Pin headers protrude ~5mm below the PCB into the cavity below
//
// Mechanical: Four risers in the corners of the inner cavity. PCB
// sits on top of the risers and is bolted down with four M2.5
// self-tapping screws that thread into the riser tops. Lid is
// snap-fit only (no screws through the lid).
//
// Slicer print orientation: base bottom-down, lid lip-up (already
// flipped in the layout block at the bottom of this file).
//
// Export each part to its own STL from the CLI:
//   openscad -D 'part="base"' -o base.stl enclosure.scad
//   openscad -D 'part="lid"'  -o lid.stl  enclosure.scad
// Or pick a part from the Customizer dropdown and File > Export > STL.

/* [Render] */
part = "base";  // [all, base, lid]

/* [Board] */
board_l       = 54.4;  // PCB length
board_w       = 28.3;  // PCB width
board_h       = 1.6;   // PCB thickness
pin_drop      = 9.0;   // header pin protrusion below PCB
// 13.5 top clearence
top_clearance = 10.0;  // tallest stuff above PCB (USB conn / RF can)

/* [PCB mounting holes] */
mount_inset_x_back  = 2.5;  // USB-end edge → mounting hole (long-axis)
mount_inset_x_front = 5.9;  // LED-end edge → mounting hole (long-axis);
                            // measured: hole centers are 46mm apart on the
                            // long axis, so 54.4 - 46 - 2.5 = 5.9
mount_inset_y       = 2.5;  // each long edge → mounting hole (short-axis)

/* [USB cutout] */
usb_w        = 9.0;    // micro-USB cutout width
usb_h        = 4.5;    // cutout height
usb_pcb_gap  = 1.5;    // gap above PCB top surface

/* [IR LED window] */
led_d = 5.4;           // 5mm LED + 0.4mm slip fit
led_z = 5;             // LED center height above inside floor (in the
                       // cavity below the PCB; max ≈ cavity_h - led_d/2)

/* [M2.5 corner risers] */
riser_size    = 6.0;   // square riser side length (fused to corner walls)
screw_pilot_d = 2.1;   // M2.5 self-tapping pilot into the riser
pilot_depth   = 6.0;   // pilot hole depth from riser top, downward

/* [Shell] */
wall        = 2;
board_clear = 0.4;     // PCB-to-wall slop (0.2mm per side)
lid_lip     = 1;
lid_gap     = 0.2;     // lid-to-base clearance
vent_slots  = 5;       // 0 disables

/* [Hidden] */
$fn = 64;
eps = 0.01;

// ---- derived ----
inner_l     = board_l + board_clear;
inner_w     = board_w + board_clear;
cavity_h    = pin_drop + 1;
shelf_top_z = wall + cavity_h;          // PCB rests at this Z
inside_h    = cavity_h + board_h + top_clearance;
out_l       = inner_l + 2*wall;
out_w       = inner_w + 2*wall;
out_h       = inside_h + wall;

// PCB origin within inner cavity (centered)
pcb_x0 = board_clear/2;
pcb_y0 = board_clear/2;

// Four risers. Each entry is [riser-corner-xy, pilot-xy] in absolute
// (post-wall) coordinates.
//
// The USB-end (back) risers are corner-anchored (touching both adjacent
// inner walls). The LED-end (front) risers slide inward along the long
// axis to match the actual PCB hole position — they remain anchored to
// the long-side wall (top/bottom in the "vertical" layout) but float
// away from the LED wall by mount_inset_x_front - 2.5mm.
//
// pilot_x_front / pilot_x_back: absolute X of pilot at each end.
// front_cube_x: X of the LED-end cube (centered on the pilot).
pilot_x_front = wall + pcb_x0 + mount_inset_x_front;
pilot_x_back  = wall + pcb_x0 + board_l - mount_inset_x_back;
front_cube_x  = pilot_x_front - riser_size/2;
back_cube_x   = wall + inner_l - riser_size;

risers = [
    // bottom-left (LED end, low Y) — anchored to bottom wall, slid inward in X
    [[front_cube_x, wall],
     [pilot_x_front, wall + pcb_y0 + mount_inset_y]],
    // bottom-right (USB end, low Y) — corner-anchored
    [[back_cube_x, wall],
     [pilot_x_back, wall + pcb_y0 + mount_inset_y]],
    // top-left (LED end, high Y) — anchored to top wall, slid inward in X
    [[front_cube_x, wall + inner_w - riser_size],
     [pilot_x_front, wall + pcb_y0 + board_w - mount_inset_y]],
    // top-right (USB end, high Y) — corner-anchored
    [[back_cube_x, wall + inner_w - riser_size],
     [pilot_x_back, wall + pcb_y0 + board_w - mount_inset_y]],
];

module base() {
    // Hollow shell with wall cutouts
    difference() {
        cube([out_l, out_w, out_h]);

        // hollow interior
        translate([wall, wall, wall])
            cube([inner_l, inner_w, inside_h + eps]);

        // USB cutout, back wall (+X)
        translate([out_l - wall - eps,
                   out_w/2 - usb_w/2,
                   shelf_top_z + board_h + usb_pcb_gap])
            cube([wall + 2*eps, usb_w, usb_h]);

        // IR LED window, front wall (-X)
        translate([-eps, out_w/2, wall + led_z])
            rotate([0, 90, 0])
                cylinder(d=led_d, h=wall + 2*eps);
    }

    // Four square corner risers fused to the adjacent inner walls.
    // Added AFTER the cavity is hollowed, otherwise they'd be subtracted out.
    for (r = risers)
        difference() {
            translate([r[0][0], r[0][1], wall])
                cube([riser_size, riser_size, cavity_h]);
            translate([r[1][0], r[1][1], wall + cavity_h - pilot_depth])
                cylinder(d=screw_pilot_d, h=pilot_depth + eps);
        }
}

module lid() {
    difference() {
        union() {
            cube([out_l, out_w, wall]);
            if (lid_lip > 0) {
                translate([wall + lid_gap, wall + lid_gap, -lid_lip])
                    cube([inner_l - 2*lid_gap,
                          inner_w - 2*lid_gap,
                          lid_lip]);
            }
        }
        if (vent_slots > 0) {
            slot_w  = 2;
            slot_l  = out_w * 0.4;
            spacing = out_l / (vent_slots + 1);
            for (i = [1:vent_slots])
                translate([i*spacing - slot_w/2,
                           (out_w - slot_l)/2,
                           -lid_lip - eps])
                    cube([slot_w, slot_l, wall + lid_lip + 2*eps]);
        }
    }
}

// Render the part(s) selected by the `part` parameter at the top.
// "all" lays out base + flipped lid side-by-side for preview.
// "base" / "lid" emit a single body in print orientation for STL export.

if (part == "all") {
    base();
    translate([0, 2*out_w + 5, wall])
        rotate([180, 0, 0])
            lid();
} else if (part == "base") {
    base();
} else if (part == "lid") {
    // Lid flipped lip-up so the plate top sits on the bed.
    translate([0, 0, wall])
        rotate([180, 0, 0])
            lid();
}
