import cadquery as cq
arm_length = 280.0
arm_width = 20.0
arm_thickness = 2.0
wood_length = 120.0
wood_width = 15.0
wood_thickness = 6.0
head_length = 40.0
head_width = 30.0
pivot_pin_radius = 3.0
pivot_pin_length = 20.0
ring_outer_radius = 12.0
ring_inner_radius = 9.0
ring_thickness = 2.0
arm1_main = cq.Workplane('XY').center(arm_length / 2, 0, 0).box(arm_length, arm_width, arm_thickness)
wood_center_x = (arm_length - wood_length) / 2 + wood_length / 2
arm1_wood = cq.Workplane('XY', origin=(wood_center_x, 0, arm_thickness / 2)).box(wood_length, wood_width, wood_thickness, centered=(True, True, False))
head_center_x = arm_length + head_length / 2
arm1_head = cq.Workplane('XY', origin=(head_center_x, 0, 0)).box(head_length, head_width, arm_thickness)
arm1 = arm1_main.add(arm1_wood).add(arm1_head)
arm2_main = cq.Workplane('XZ').center(arm_length / 2, 0, 0).box(arm_length, arm_thickness, arm_width)
arm2_wood = cq.Workplane('XZ', origin=(wood_center_x, arm_thickness / 2, 0)).box(wood_length, wood_thickness, wood_width, centered=(True, False, True))
arm2_head = cq.Workplane('XZ', origin=(head_center_x, 0, 0)).box(head_length, arm_thickness, head_width)
arm2 = arm2_main.add(arm2_wood).add(arm2_head)
pivot_pin = cq.Workplane('YZ').cylinder(height=pivot_pin_length, radius=pivot_pin_radius)
hanging_ring = cq.Workplane('YZ', origin=(-ring_outer_radius, 0, 0)).circle(ring_outer_radius).extrude(ring_thickness).faces('>X').workplane().circle(ring_inner_radius).extrude(-ring_thickness, combine='cut')
result = arm1.add(arm2).add(pivot_pin).add(hanging_ring)