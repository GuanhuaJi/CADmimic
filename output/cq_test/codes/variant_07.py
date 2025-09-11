import cadquery as cq
arm_length = 300
arm_width = 20
head_width = 25
metal_thickness = 2
wood_length = 120
wood_width = 18
wood_height = 6
pivot_x_pos = 15
pivot_hole_radius = 4
pivot_pin_radius = 3.8
open_angle = 20
arm_profile = cq.Workplane('XY').polyline([(0, -arm_width / 2), (arm_length - 40, -arm_width / 2), (arm_length - 40, -head_width / 2), (arm_length, -head_width / 2), (arm_length, head_width / 2), (arm_length - 40, head_width / 2), (arm_length - 40, arm_width / 2), (0, arm_width / 2)]).close()
arm_metal = arm_profile.extrude(metal_thickness)
arm_wood = cq.Workplane('XY').box(wood_length, wood_width, wood_height).translate((wood_length / 2 + 20, 0, metal_thickness / 2 + wood_height / 2))
one_arm_solid = arm_metal.add(arm_wood)
one_arm_template = one_arm_solid.faces('>Z').workplane().moveTo(pivot_x_pos, 0).circle(pivot_hole_radius).extrude(-(metal_thickness + wood_height), combine='cut')
arm1 = one_arm_template.rotate((pivot_x_pos, 0, 0), (pivot_x_pos, 1, 0), open_angle / 2)
arm_metal_2 = arm_profile.extrude(metal_thickness)
arm_wood_2 = cq.Workplane('XY').box(wood_length, wood_width, wood_height).translate((wood_length / 2 + 20, 0, metal_thickness / 2 + wood_height / 2))
one_arm_solid_2 = arm_metal_2.add(arm_wood_2)
one_arm_template_2 = one_arm_solid_2.faces('>Z').workplane().moveTo(pivot_x_pos, 0).circle(pivot_hole_radius).extrude(-(metal_thickness + wood_height), combine='cut')
arm2 = one_arm_template_2.rotate((pivot_x_pos, 0, 0), (pivot_x_pos, 1, 0), -open_angle / 2)
pin_height = arm_width + 4
pivot_pin = cq.Workplane('XZ').circle(pivot_pin_radius).extrude(pin_height).translate((pivot_x_pos, -pin_height / 2, 0))
result = arm1.add(arm2).add(pivot_pin)