import cadquery as cq
arm_length = 300
arm_width = 20
arm_thickness = 1.5
head_length = 70
head_width = 28
wood_length = 120
wood_width = 18
wood_thickness = 10
hinge_hole_radius = 3.0
pin_radius = 2.9
pin_height = arm_thickness * 2 + 2
ring_outer_radius = 15
ring_inner_radius = 12
ring_thickness = 2
open_angle = 20.0
head_start_x = arm_length - head_length
arm_profile = cq.Workplane('XY').moveTo(0, -arm_width / 2).lineTo(head_start_x, -arm_width / 2).lineTo(arm_length, -head_width / 2).lineTo(arm_length, head_width / 2).lineTo(head_start_x, arm_width / 2).lineTo(0, arm_width / 2).close()
metal_arm = arm_profile.extrude(arm_thickness)
metal_arm = metal_arm.workplane().moveTo(0, 0).circle(hinge_hole_radius).cutThruAll()
scallop_radius = 7
scallop_positions = [arm_length - 55, arm_length - 30, arm_length - 5]
for x_pos in scallop_positions:
    metal_arm = metal_arm.moveTo(x_pos, head_width / 2).circle(scallop_radius).cutThruAll()
    metal_arm = metal_arm.moveTo(x_pos, -head_width / 2).circle(scallop_radius).cutThruAll()
wood_grip = cq.Workplane('XY').box(wood_length, wood_width, wood_thickness)
pin = cq.Workplane('XY').cylinder(pin_height, pin_radius)
ring = cq.Workplane('XY').circle(ring_outer_radius).circle(ring_inner_radius).extrude(ring_thickness)
result = cq.Assembly()
silver_color = cq.Color(0.75, 0.75, 0.75)
wood_color = cq.Color(0.6, 0.4, 0.2)
z_offset_arm = arm_thickness / 2
z_offset_wood = z_offset_arm + arm_thickness / 2 + wood_thickness / 2
wood_x_pos = 70
angle_r = open_angle / 2
metal_arm_r = metal_arm.translate((0, 0, z_offset_arm)).rotate((0, 0, 0), (0, 0, 1), angle_r)
wood_grip_r = wood_grip.translate((wood_x_pos, 0, z_offset_wood)).rotate((0, 0, 0), (0, 0, 1), angle_r)
angle_l = -open_angle / 2
metal_arm_l = metal_arm.translate((0, 0, -z_offset_arm)).rotate((0, 0, 0), (0, 0, 1), angle_l)
wood_grip_l = wood_grip.translate((wood_x_pos, 0, -z_offset_wood)).rotate((0, 0, 0), (0, 0, 1), angle_l)
ring_translated = ring.translate((15, 0, 0))
result.add(metal_arm_r, name='metal_arm_right', color=silver_color)
result.add(wood_grip_r, name='wood_grip_right', color=wood_color)
result.add(metal_arm_l, name='metal_arm_left', color=silver_color)
result.add(wood_grip_l, name='wood_grip_left', color=wood_color)
result.add(pin, name='pin', color=silver_color)
result.add(ring_translated, name='ring', color=silver_color)