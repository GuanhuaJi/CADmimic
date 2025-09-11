import cadquery as cq
arm_length = 280.0
arm_width = 20.0
arm_thickness = 2.0
gap_between_arms = 15.0
handle_length = 120.0
handle_width = 18.0
handle_thickness = 8.0
hinge_pin_hole_radius = 4.0
hanging_loop_outer_radius = 15.0
hanging_loop_thickness = 3.0
total_width = 2 * arm_width + gap_between_arms
tongs_body = cq.Workplane('XY').rect(arm_length, total_width).extrude(arm_thickness).center(0, 0).rect(arm_length, gap_between_arms).extrude(-arm_thickness, combine='cut')
handles = tongs_body.faces('>Z').workplane().center(arm_length / 4, (gap_between_arms + arm_width) / 2).rect(handle_length, handle_width).center(0, -(gap_between_arms + arm_width)).rect(handle_length, handle_width).extrude(handle_thickness)
result = handles.faces('<X').workplane(offset=5).circle(hanging_loop_outer_radius).circle(hanging_loop_outer_radius - hanging_loop_thickness).extrude(arm_thickness)