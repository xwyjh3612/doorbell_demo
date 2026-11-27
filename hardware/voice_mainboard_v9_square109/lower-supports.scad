// Voice intercom V9 • two insulating lower supports, provisional dimensions (mm).
// Z in assembly: PCB front surface = 0, rear of shell = positive.
// Measure the lower post seat and screw/thread engagement before printing for fit.
part = "print"; // [print,assembly,left,right]
pcb_thickness = 1.6;
post_seat_z = 0;
rail_thickness = 3.2;
rail_width = 8.4;
pcb_screw_d = 3.2;
shell_screw_d = 4.0;
$fn = 64;

// Same front-view coordinates used by the 1:1 shell overlay.
left = [[11,64], [1,65], [0,109]];
right = [[103,64], [108,65], [109,109]];

module disk_at(pt, diameter) {
    translate(pt) circle(d=diameter);
}

module support(pts) {
    // Bracket body and post seat use a continuous spine; the lower end has a
    // step so that the top of the PCB can still sit at the upper screw datum.
    seat_top = post_seat_z;
    seat_end = pcb_thickness+rail_thickness;
    assert(post_seat_z <= pcb_thickness, "Measure the lower post and adjust the standoff stack");
    difference() {
        union() {
            translate([0,0,pcb_thickness]) linear_extrude(rail_thickness) {
                for (i=[0:len(pts)-2]) hull() {
                    disk_at(pts[i],rail_width);
                    disk_at(pts[i+1],rail_width);
                }
            }
            translate([0,0,seat_top]) linear_extrude(seat_end-seat_top)
                disk_at(pts[2],rail_width);
        }
        translate([0,0,seat_top-0.1]) linear_extrude(seat_end-seat_top+0.2) {
            disk_at(pts[0],pcb_screw_d);
            disk_at(pts[2],shell_screw_d);
        }
    }
}

// Turn the flat rear faces down onto the print bed and separate the pieces.
module flat(pts, offset) {
    translate([offset-pts[2][0],pts[2][1],pcb_thickness+rail_thickness])
        rotate([180,0,0]) support(pts);
}

if (part=="assembly") {
    support(left);
    support(right);
} else if (part=="left") {
    flat(left,0);
} else if (part=="right") {
    flat(right,0);
} else {
    flat(left,0);
    flat(right,30);
}
