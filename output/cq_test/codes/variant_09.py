import cadquery as cq
handle_length = 250.0
handle_width = 20.0
handle_height = 12.0
metal_thickness = 1.5
head_length = 50.0
head_width = 25.0
head_height = 4.0
handle = cq.Workplane('XY').box(handle_length, handle_width, handle_height).faces('>Z').workplane().rect(handle_length, handle_width - 2 * metal_thickness).extrude(-(handle_height - metal_thickness), combine='cut')
head_added = handle.faces('>X').workplane().box(head_length, head_width, head_height, centered=(False, True, True))
result = head_added.faces('<X').workplane().circle(4.0).extrude(handle_width, combine='cut')