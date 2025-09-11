import cadquery as cq
arm_length = 280.0
arm_width = 20.0
arm_thickness = 2.0
handle_length = 120.0
handle_width = 16.0
handle_thickness = 8.0
handle_x_offset = -60.0
head_length = 30.0
head_width = arm_width
head_thickness = arm_thickness
gap = 4.0
hinge_pin_radius = 2.5
hinge_x_pos = -arm_length / 2.0
ring_major_radius = 12.0
ring_minor_radius = 2.0
ring_x_pos = hinge_x_pos - ring_major_radius - 2.0
z_top_offset = gap / 2.0
top_arm_main = cq.Workplane('XY').workplane(offset=z_top_offset).box(arm_length, arm_width, arm_thickness, centered=(True, True, False))
handle_z_offset = z_top_offset + arm_thickness
top_handle = cq.Workplane('XY').workplane(offset=handle_z_offset).center(handle_x_offset, 0).box(handle_length, handle_width, handle_thickness, centered=(True, True, False))
head_x_pos = arm_length / 2.0 - head_thickness / 2.0
head_z_pos = z_top_offset + arm_thickness - head_length / 2.0
top_head = cq.Workplane('XZ').center(head_x_pos, 0, head_z_pos).box(head_thickness, head_width, head_length)
z_bottom_offset = -gap / 2.0
bottom_arm_main = cq.Workplane('XY').workplane(offset=z_bottom_offset).box(arm_length, arm_width, -arm_thickness, centered=(True, True, False))
handle_z_offset_bottom = z_bottom_offset - arm_thickness
bottom_handle = cq.Workplane('XY').workplane(offset=handle_z_offset_bottom).center(handle_x_offset, 0).box(handle_length, handle_width, -handle_thickness, centered=(True, True, False))
head_z_pos_bottom = z_bottom_offset - arm_thickness + head_length / 2.0
bottom_head = cq.Workplane('XZ').center(head_x_pos, 0, head_z_pos_bottom).box(head_thickness, head_width, head_length)
pin_height = gap + 2 * arm_thickness
hinge_pin = cq.Workplane('XY').center(hinge_x_pos, 0).circle(hinge_pin_radius).extrude(pin_height)
ring = cq.Solid.makeTorus(ring_major_radius, ring_minor_radius, pnt=(ring_x_pos, 0, 0), dir=(1, 0, 0))
result = cq.Workplane('XY').add(top_arm_main).add(top_handle).add(top_head).add(bottom_arm_main).add(bottom_handle).add(bottom_head).add(hinge_pin).add(ring)