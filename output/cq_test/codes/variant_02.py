import cadquery as cq
final_arm_length = 260.0
pivot_offset_from_end = 20.0
arm_width = 20.0
head_width = 28.0
head_length = 40.0
arm_thickness = 2.0
pivot_hole_radius = 4.0
x_pivot = 0.0
x_back = -pivot_offset_from_end
x_front = x_pivot + final_arm_length
x_head_start = x_front - head_length
wood_length = 110.0
wood_width = 15.0
wood_height = 8.0
wood_offset_from_pivot = 25.0
open_angle = 10.0
arm_contour = [(x_back, -arm_width / 2), (x_pivot, -arm_width / 2), (x_head_start, -arm_width / 2), (x_front, -head_width / 2), (x_front, head_width / 2), (x_head_start, arm_width / 2), (x_pivot, arm_width / 2), (x_back, arm_width / 2)]
metal_arm_solid = cq.Workplane('XY').polyline(arm_contour).close().extrude(arm_thickness)
metal_arm = metal_arm_solid.faces('>Z').workplane().moveTo(x_pivot, 0).circle(pivot_hole_radius).extrude(-arm_thickness, combine='cut')
wood_handle = cq.Workplane('XY').box(wood_length, wood_width, wood_height, centered=True)
pin_height = arm_thickness * 2 + 1.0
pivot_pin = cq.Workplane('XY').cylinder(pin_height, pivot_hole_radius, centered=True)
end_cap = cq.Workplane('YZ').box(10, arm_width, 15, centered=True)
pull_ring = cq.Solid.makeTorus(14, 3, dir=(1, 0, 0))
metal_color = cq.Color(0.78, 0.78, 0.82)
wood_color = cq.Color(0.8, 0.65, 0.45)
top_arm_assy = cq.Assembly()
top_arm_assy.add(metal_arm, name='metal_part', color=metal_color)
wood_pos_top = cq.Vector(x_pivot + wood_offset_from_pivot + wood_length / 2, 0, arm_thickness / 2 + wood_height / 2)
top_arm_assy.add(wood_handle, name='wood_part', color=wood_color, loc=cq.Location(wood_pos_top))
bottom_arm_assy = cq.Assembly()
bottom_arm_assy.add(metal_arm, name='metal_part', color=metal_color)
wood_pos_bottom = cq.Vector(x_pivot + wood_offset_from_pivot + wood_length / 2, 0, -(arm_thickness / 2 + wood_height / 2))
bottom_arm_assy.add(wood_handle, name='wood_part', color=wood_color, loc=cq.Location(wood_pos_bottom))
result = cq.Assembly(name='kitchen_tongs')
result.add(top_arm_assy, name='top_arm', loc=cq.Location(cq.Vector(0, 0, arm_thickness / 2), cq.Vector(0, 0, 1), open_angle))
result.add(bottom_arm_assy, name='bottom_arm', loc=cq.Location(cq.Vector(0, 0, -arm_thickness / 2), cq.Vector(0, 0, 1), -open_angle))
result.add(pivot_pin, name='pivot_pin', color=metal_color)
result.add(end_cap, name='end_cap', color=metal_color, loc=cq.Location(cq.Vector(x_back - 5, 0, 0)))
result.add(pull_ring, name='pull_ring', color=metal_color, loc=cq.Location(cq.Vector(x_back - 15, 0, 0)))