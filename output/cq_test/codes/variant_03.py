import cadquery as cq
arm_thickness = 1.5
handle_width = 20.0
head_width = 35.0
total_length = 270.0
handle_length = 100.0
pivot_hole_dia = 5.0
pivot_from_end = 25.0
ring_hole_dia = 5.0
wood_length = 80.0
wood_width = 18.0
wood_thickness = 6.0
pivot_pin_height = 4.0
open_angle = 15.0
p0 = (-pivot_from_end, -handle_width / 2.0)
p1 = (handle_length - pivot_from_end, -handle_width / 2.0)
p2 = (total_length - pivot_from_end - 30, -head_width / 2.0)
p3 = (total_length - pivot_from_end - 15, -(head_width / 2.0 - 5))
p4 = (total_length - pivot_from_end, -head_width / 2.0)
p5 = (total_length - pivot_from_end, head_width / 2.0)
p6 = (total_length - pivot_from_end - 15, head_width / 2.0 - 5)
p7 = (total_length - pivot_from_end - 30, head_width / 2.0)
p8 = (handle_length - pivot_from_end, handle_width / 2.0)
p9 = (-pivot_from_end, handle_width / 2.0)
arm_profile = cq.Workplane('XY').polyline([p0, p1, p2, p3, p4, p5, p6, p7, p8, p9]).close()
arm_metal = arm_profile.extrude(arm_thickness)
arm_metal = arm_metal.faces('>Z').workplane().moveTo(0, 0).circle(pivot_hole_dia / 2.0).moveTo(-pivot_from_end + 10, 0).circle(ring_hole_dia / 2.0).extrude(-arm_thickness, combine='cut')
wood_grip = cq.Workplane('XY').box(wood_length, wood_width, wood_thickness)
pivot_pin = cq.Workplane('XY').cylinder(height=pivot_pin_height, radius=pivot_hole_dia / 2.0, centered=True)
locking_ring = cq.Solid.makeTorus(12, 1.5)
metal_color = cq.Color(0.75, 0.75, 0.79)
wood_color = cq.Color(0.87, 0.72, 0.53)
arm_assy = cq.Assembly(name='arm')
arm_assy.add(arm_metal, name='metal', color=metal_color)
wood_center_x = handle_length / 2.0 - pivot_from_end
wood_center_z = arm_thickness + wood_thickness / 2.0
wood_loc = cq.Location(cq.Vector(wood_center_x, 0, wood_center_z))
arm_assy.add(wood_grip, name='wood', color=wood_color, loc=wood_loc)
tongs_assy = cq.Assembly(name='tongs')
loc_arm1 = cq.Location(cq.Vector(0, 0, -pivot_pin_height / 2.0))
tongs_assy.add(arm_assy, name='arm1', loc=loc_arm1)
loc_flip = cq.Location(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 180)
loc_move = cq.Location(cq.Vector(0, 0, pivot_pin_height / 2.0))
loc_open = cq.Location(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), open_angle)
loc_arm2 = loc_open * loc_move * loc_flip
tongs_assy.add(arm_assy, name='arm2', loc=loc_arm2)
tongs_assy.add(pivot_pin, name='pivot', color=metal_color)
ring_pos_x = -pivot_from_end + 10
ring_loc = cq.Location(cq.Vector(ring_pos_x, 0, 0), cq.Vector(0, 1, 0), 90)
tongs_assy.add(locking_ring, name='ring', color=metal_color, loc=ring_loc)
result = tongs_assy