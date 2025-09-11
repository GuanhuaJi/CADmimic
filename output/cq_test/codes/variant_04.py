import cadquery as cq
length_total = 300
length_handle_part = 240
width_handle = 18
width_jaw_tip = 30
thickness_metal = 2
hole_dist_from_end = 20
hole_radius = 4
handle_length = 130
handle_width = 18
handle_thickness = 8
handle_offset_from_end = 40
ring_major_radius = 14
ring_minor_radius = 2.5
ring_offset_from_end = -10
silver_color = cq.Color(0.75, 0.75, 0.75)
wood_color = cq.Color(0.6, 0.4, 0.2)
metal_profile = cq.Workplane('XY').polyline([(0, -width_handle / 2), (length_handle_part, -width_handle / 2), (length_total, -width_jaw_tip / 2), (length_total, width_jaw_tip / 2), (length_handle_part, width_handle / 2), (0, width_handle / 2)]).close()
arm1_metal = metal_profile.extrude(-thickness_metal)
arm1_metal = arm1_metal.faces('<Z').workplane().moveTo(hole_dist_from_end, 0).circle(hole_radius).extrude(thickness_metal, combine='cut')
handle1 = cq.Workplane('XY', origin=(handle_offset_from_end + handle_length / 2, 0, -thickness_metal - handle_thickness / 2)).box(handle_length, handle_width, handle_thickness)
arm2_metal = metal_profile.extrude(thickness_metal)
arm2_metal = arm2_metal.faces('<Z').workplane().moveTo(hole_dist_from_end, 0).circle(hole_radius).extrude(-thickness_metal, combine='cut')
handle2 = cq.Workplane('XY', origin=(handle_offset_from_end + handle_length / 2, 0, thickness_metal + handle_thickness / 2)).box(handle_length, handle_width, handle_thickness)
pin = cq.Workplane('XZ', origin=(hole_dist_from_end, 0, 0)).cylinder(2 * thickness_metal, hole_radius)
ring = cq.Solid.makeTorus(ring_major_radius, ring_minor_radius, pnt=(ring_offset_from_end, 0, 0), dir=(1, 0, 0))
tongs_assembly = cq.Assembly(name='tongs').add(arm1_metal, name='bottom_arm_metal', color=silver_color).add(handle1, name='bottom_arm_handle', color=wood_color).add(arm2_metal, name='top_arm_metal', color=silver_color).add(handle2, name='top_arm_handle', color=wood_color).add(pin, name='hinge_pin', color=silver_color).add(ring, name='hanger_ring', color=silver_color)
result = tongs_assembly