extends Node3D
## Genera vegetazione procedurale (alberi) dentro le aree verdi lette da
## data/osm/green.geojson, usando MultiMeshInstance3D per l'instancing
## (prestazioni), come richiesto dalla spec del progetto ("area verde ->
## generatore di vegetazione -> alberi + cespugli + erba", con
## "eventualmente MultiMesh in Godot").
##
## Placeholder volutamente semplice per l'MVP: non serve rappresentare ogni
## albero reale, solo una densita' plausibile (vedi milestone 1/2 nel README).

const GREEN_GEOJSON_PATH := "res://data/osm/green.geojson"

@export var trees_per_100sqm: float = 1.2
@export var min_spacing_m: float = 3.0
@export var trunk_height: float = 2.2
@export var trunk_radius: float = 0.12
@export var foliage_radius: float = 1.4
@export var foliage_height: float = 3.0
@export var max_trees_per_area: int = 4000

var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	_rng.randomize()
	_generate()


func _generate() -> void:
	var json_text := _read_file(GREEN_GEOJSON_PATH)
	if json_text.is_empty():
		var msg := "vegetation_scatter: %s non trovato o vuoto, " % GREEN_GEOJSON_PATH
		msg += "nessun albero generato."
		push_warning(msg)
		return

	var data = JSON.parse_string(json_text)
	if data == null or typeof(data) != TYPE_DICTIONARY or not data.has("features"):
		push_warning("vegetation_scatter: GeoJSON non valido in %s." % GREEN_GEOJSON_PATH)
		return

	var placements: Array = []  # ogni elemento: {"pos": Vector2, "rot": float, "scale": float}

	for feature in data["features"]:
		var geometry: Dictionary = feature.get("geometry", {})
		if geometry.get("type") != "Polygon":
			continue
		var ring: Array = geometry["coordinates"][0]
		placements.append_array(_sample_points_in_polygon(ring))

	if placements.is_empty():
		print("vegetation_scatter: nessuna area verde con spazio sufficiente, nessun albero generato.")
		return

	var trunk_mesh := _make_trunk_mesh()
	var foliage_mesh := _make_foliage_mesh()
	var foliage_offset := trunk_height + foliage_height * 0.5
	_spawn_multimesh(placements, "TreeTrunks", trunk_mesh, trunk_height * 0.5)
	_spawn_multimesh(placements, "TreeFoliage", foliage_mesh, foliage_offset)

	print("vegetation_scatter: generati %d alberi." % placements.size())


func _read_file(path: String) -> String:
	if not FileAccess.file_exists(path):
		return ""
	var f := FileAccess.open(path, FileAccess.READ)
	var text := f.get_as_text()
	f.close()
	return text


func _sample_points_in_polygon(ring: Array) -> Array:
	var poly := PackedVector2Array()
	for pt in ring:
		# GeoJSON contiene [x, z] in metri (vedi pipeline/coords.py). Qui
		# lavoriamo in 2D (x, z); l'altezza (y) viene aggiunta solo quando
		# posizioniamo le mesh in _spawn_multimesh.
		poly.append(Vector2(pt[0], pt[1]))

	if poly.size() < 3:
		return []

	var min_x: float = poly[0].x
	var max_x: float = poly[0].x
	var min_y: float = poly[0].y
	var max_y: float = poly[0].y
	for p in poly:
		min_x = min(min_x, p.x)
		max_x = max(max_x, p.x)
		min_y = min(min_y, p.y)
		max_y = max(max_y, p.y)

	var area_sqm: float = max(0.0, max_x - min_x) * max(0.0, max_y - min_y)
	var target_count: int = clampi(int(area_sqm / 100.0 * trees_per_100sqm), 0, max_trees_per_area)

	var placed_positions: Array = []
	var placements: Array = []
	var attempts := 0
	var max_attempts := maxi(target_count * 20, 50)

	while placed_positions.size() < target_count and attempts < max_attempts:
		attempts += 1
		var candidate := Vector2(
			_rng.randf_range(min_x, max_x),
			_rng.randf_range(min_y, max_y)
		)
		if not Geometry2D.is_point_in_polygon(candidate, poly):
			continue

		var too_close := false
		for other in placed_positions:
			if candidate.distance_to(other) < min_spacing_m:
				too_close = true
				break
		if too_close:
			continue

		placed_positions.append(candidate)
		placements.append({
			"pos": candidate,
			"rot": _rng.randf_range(0.0, TAU),
			"scale": _rng.randf_range(0.8, 1.3),
		})

	return placements


func _spawn_multimesh(
	placements: Array, node_name: String, mesh: Mesh, height_offset: float
) -> void:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	mm.instance_count = placements.size()

	for i in placements.size():
		var p: Dictionary = placements[i]
		var s: float = p["scale"]
		var t := Transform3D()
		t = t.rotated(Vector3.UP, p["rot"])
		t = t.scaled(Vector3(s, s, s))
		t.origin = Vector3(p["pos"].x, height_offset * s, p["pos"].y)
		mm.set_instance_transform(i, t)

	var mmi := MultiMeshInstance3D.new()
	mmi.name = node_name
	mmi.multimesh = mm
	add_child(mmi)


func _make_trunk_mesh() -> Mesh:
	var mesh := CylinderMesh.new()
	mesh.top_radius = trunk_radius
	mesh.bottom_radius = trunk_radius * 1.3
	mesh.height = trunk_height
	mesh.material = _make_material(Color(0.35, 0.24, 0.15))
	return mesh


func _make_foliage_mesh() -> Mesh:
	var mesh := CylinderMesh.new()
	mesh.top_radius = 0.0
	mesh.bottom_radius = foliage_radius
	mesh.height = foliage_height
	mesh.material = _make_material(Color(0.16, 0.38, 0.14))
	return mesh


func _make_material(color: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	return mat
