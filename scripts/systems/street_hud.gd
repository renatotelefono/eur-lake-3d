extends CanvasLayer
## HUD minimale che mostra il nome della strada/sentiero piu' vicino al
## giocatore, per orientarsi mentre si esplora ("capire dove sto andando").
##
## Legge roads.geojson e paths.geojson (stesso formato di
## vegetation_scatter.gd/world.gd), precalcola i segmenti che hanno un tag
## "name" in OpenStreetMap, poi ad intervalli regolari cerca il segmento piu'
## vicino alla posizione del giocatore e aggiorna una Label in overlay.
##
## Le strade/sentieri senza nome (frequenti nei sentieri secondari di un
## parco) vengono ignorati: se il piu' vicino non ha nome, l'etichetta resta
## vuota piuttosto che mostrare qualcosa di fuorviante.

const ROADS_GEOJSON_PATH := "res://data/osm/roads.geojson"
const PATHS_GEOJSON_PATH := "res://data/osm/paths.geojson"
const UPDATE_INTERVAL_SEC := 0.3
const MAX_DISTANCE_M := 40.0  # oltre questa distanza dal segmento piu' vicino, nessuna etichetta

var _player: Node3D
var _label: Label
# ogni elemento: {"a": Vector2, "b": Vector2, "name": String, "kind": String}
var _segments: Array = []
var _timer := 0.0
var _current_text := ""


func setup(player: Node3D) -> void:
	_player = player


func _ready() -> void:
	layer = 10
	_build_label()
	_segments = _load_named_segments(ROADS_GEOJSON_PATH, "Strada")
	_segments.append_array(_load_named_segments(PATHS_GEOJSON_PATH, "Sentiero"))
	print("street_hud: %d segmenti con nome caricati." % _segments.size())


func _build_label() -> void:
	_label = Label.new()
	_label.name = "StreetNameLabel"
	_label.add_theme_font_size_override("font_size", 22)
	_label.add_theme_color_override("font_color", Color(1, 1, 1))
	_label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.85))
	_label.add_theme_constant_override("shadow_offset_x", 2)
	_label.add_theme_constant_override("shadow_offset_y", 2)
	_label.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_label.position.y = -48
	_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_label.text = ""
	add_child(_label)


func _load_named_segments(path: String, kind: String) -> Array:
	var segments: Array = []
	if not FileAccess.file_exists(path):
		return segments

	var f := FileAccess.open(path, FileAccess.READ)
	var text := f.get_as_text()
	f.close()

	var data = JSON.parse_string(text)
	if data == null or typeof(data) != TYPE_DICTIONARY or not data.has("features"):
		return segments

	for feature in data["features"]:
		var properties: Dictionary = feature.get("properties", {})
		var name_value = properties.get("name")
		if name_value == null or String(name_value).is_empty():
			continue

		var geometry: Dictionary = feature.get("geometry", {})
		if geometry.get("type") != "LineString":
			continue

		var coords: Array = geometry["coordinates"]
		for i in range(coords.size() - 1):
			segments.append({
				"a": Vector2(coords[i][0], coords[i][1]),
				"b": Vector2(coords[i + 1][0], coords[i + 1][1]),
				"name": String(name_value),
				"kind": kind,
			})

	return segments


func _process(delta: float) -> void:
	if _player == null or _segments.is_empty():
		return
	_timer -= delta
	if _timer > 0.0:
		return
	_timer = UPDATE_INTERVAL_SEC
	_update_label()


func _update_label() -> void:
	var pos := Vector2(_player.global_position.x, _player.global_position.z)
	var best_dist := INF
	var best_name := ""
	var best_kind := ""

	for seg in _segments:
		var d := _distance_point_segment(pos, seg["a"], seg["b"])
		if d < best_dist:
			best_dist = d
			best_name = seg["name"]
			best_kind = seg["kind"]

	if best_dist <= MAX_DISTANCE_M:
		var display := "%s: %s" % [best_kind, best_name]
		if display != _current_text:
			_current_text = display
			_label.text = _current_text
	elif _current_text != "":
		_current_text = ""
		_label.text = ""


func _distance_point_segment(p: Vector2, a: Vector2, b: Vector2) -> float:
	var ab := b - a
	var len_sq := ab.length_squared()
	if len_sq < 1e-9:
		return p.distance_to(a)
	var t: float = clamp((p - a).dot(ab) / len_sq, 0.0, 1.0)
	var projection := a + ab * t
	return p.distance_to(projection)