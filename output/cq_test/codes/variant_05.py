import cadquery as cq
arm_length = 250
arm_width = 20
arm_thickness = 4
head_length = 40
head_max_width = 30
wood_length = 100
wood_width = 22
wood_thickness = 8
pivot_pin_pos_x = 15
pivot_pin_radius = 3
pivot_pin_length = 30
ring_pos_x = 0
ring_major_radius = 15
ring_minor_radius = 4
main_bar = cq.Workplane('XY').box(arm_length, arm_width, arm_thickness, centered=(False, True, True))
head = cq.Workplane('XY').moveTo(arm_length, 0).polyline([(0, -arm_width / 2), (head_length, -head_max_width / 2), (head_length, head_max_width / 2), (0, arm_width / 2)]).close().extrude(arm_thickness)
metal_arm_solid = main_bar.union(head)
hole_cutter = cq.Workplane('XZ').cylinder(pivot_pin_length, pivot_pin_radius)
metal_arm_part = metal_arm_solid.cut(hole_cutter.translate((pivot_pin_pos_x, 0, 0)))
wood_handle_part = cq.Workplane('XY').box(wood_length, wood_width, wood_thickness)
pivot_pin_part = cq.Workplane('XZ').cylinder(pivot_pin_length, pivot_pin_radius)
ring_solid = cq.Solid.makeTorus(ring_major_radius, ring_minor_radius)
locking_ring_part = cq.Workplane('XY').add(ring_solid).rotate((0, 0, 0), (0, 1, 0), 90)
tongs_assembly = cq.Assembly()
steel_color = cq.Color(0.75, 0.75, 0.78)
wood_color = cq.Color(0.65, 0.5, 0.4)
arm = cq.Assembly()
arm.add(metal_arm_part, name='metal_arm', color=steel_color)
wood_location = cq.Location(cq.Vector(arm_length / 3, 0, arm_thickness / 2 + wood_thickness / 2))
arm.add(wood_handle_part, name='wood_handle', loc=wood_location, color=wood_color)
open_angle = 12
tongs_assembly.add(arm, name='top_arm', loc=cq.Location(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), open_angle))
tongs_assembly.add(arm, name='bottom_arm', loc=cq.Location(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), -open_angle))
pin_location = cq.Location(cq.Vector(pivot_pin_pos_x, 0, 0))
tongs_assembly.add(pivot_pin_part, name='pivot_pin', loc=pin_location, color=steel_color)
ring_location = cq.Location(cq.Vector(ring_pos_x, 0, 0))
tongs_assembly.add(locking_ring_part, name='locking_ring', loc=ring_location, color=steel_color)
result = tongs_assembly