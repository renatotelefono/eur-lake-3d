extends Control
## Minimappa in overlay (angolo in alto a destra) che mostra strade,
## sentieri, acqua e la posizione/orientamento del giocatore, per capire
## dove ci si trova rispetto alla rete stradale.
##
## Vista dall'alto, nord sempre in alto (nessuna rotazione della mappa al
## girare della telecamera): disegnata con Control._draw() a partire dagli
## stessi GeoJSON usati altrove (data/osm/*.geojson), niente camera/viewport
## 3D aggiuntiva - piu' leggero e coerente con lo stile "carica dati GeoJSON
## e disegna" gia' usato in street_hud.gd/vegetation_scatter.gd.
##
## Il nodo va aggiunto dentro un CanvasLayer (vedi world.gd:
## _spawn_minimap()) perche' Control da solo non garantisce l'overlay sopra
## la scena 3D in ogni configurazione; CanvasLayer si occupa di questo.

const ROADS_GEOJSON_PATH := "res://data/osm/roads.geojson"
const PATHS_GEOJSON_PATH := "res://data/osm/paths.geojson"
const WATER_GEOJSON_PATH := "res://data/osm/water.geojson"
const BUILDINGS_GEOJSON_PATH := "res://data/osm/buildings.geojson"

const MAP_SIZE_PX := 140.0
const VIEW_RADIUS_M := 120.0  # raggio di mondo (in metri) visibile attorno al giocatore
const MARGIN_PX := 16.0
const TELEPORT_SEARCH_STEP_M := 3.0
const TELEPORT_SEARCH_MAX_RADIUS_M := 60.0

var _player: Node3D
var _roads: Array = []  # Array di PackedVector2Array (una polilinea per elemento)
var _paths: Array = []
var _water_polys: Array = []  # Array di PackedVector2Array
var _building_polys: Array = []  # Array di PackedVector2Array


func setup(player: Node3D) -> void:
	_player = player


func _ready() -> void:
	custom_minimum_size = Vector2(MAP_SIZE_PX, MAP_SIZE_PX)
	size = Vector2(MAP_SIZE_PX, MAP_SIZE_PX)
	var viewport_size := get_viewport_rect().size
	position = Vector2(viewport_size.x - MAP_SIZE_PX - MARGIN_PX, MARGIN_PX)
	# STOP (non IGNORE) perche' ora la minimappa e' cliccabile: un clic sopra
	# di essa deve teletrasportare il giocatore, non passare attraverso.
	# Funziona quando il mouse non e' catturato (Esc per liberarlo), perche'
	# con il cursore catturato/nascosto per la visuale in terza persona non
	# c'e' un vero puntatore libero da testare contro il riquadro.
	mouse_filter = Control.MOUSE_FILTER_STOP
	clip_contents = true

	_roads = _load_lines(ROADS_GEOJSON_PATH)
	_paths = _load_lines(PATHS_GEOJSON_PATH)
	_water_polys = _load_polygons(WATER_GEOJSON_PATH)
	_building_polys = _load_polygons(BUILDINGS_GEOJSON_PATH)

	var msg := "minimap: %d strade, %d sentieri, %d specchi d'acqua, %d edifici caricati."
	print(msg % [_roads.size(), _paths.size(), _water_polys.size(), _building_polys.size()])


func _process(_delta: float) -> void:
	if _player != null:
		queue_redraw()


func _load_lines(path: String) -> Array:
	var lines: Array = []
	if not FileAccess.file_exists(path):
		return lines

	var f := FileAccess.open(path, FileAccess.READ)
	var text := f.get_as_text()
	f.close()

	var data = JSON.parse_string(text)
	if data == null or typeof(data) != TYPE_DICTIONARY or not data.has("features"):
		return lines

	for feature in data["features"]:
		var geometry: Dictionary = feature.get("geometry", {})
		if geometry.get("type") != "LineString":
			continue
		var coords: Array = geometry["coordinates"]
		var pts := PackedVector2Array()
		for pt in coords:
			pts.append(Vector2(pt[0], pt[1]))
		if pts.size() >= 2:
			lines.append(pts)

	return lines


func _load_polygons(path: String) -> Array:
	var polygons: Array = []
	if not FileAccess.file_exists(path):
		return polygons

	var f := FileAccess.open(path, FileAccess.READ)
	var text := f.get_as_text()
	f.close()

	var data = JSON.parse_string(text)
	if data == null or typeof(data) != TYPE_DICTIONARY or not data.has("features"):
		return polygons

	for feature in data["features"]:
		var geometry: Dictionary = feature.get("geometry", {})
		if geometry.get("type") != "Polygon":
			continue
		var ring: Array = geometry["coordinates"][0]
		var poly := PackedVector2Array()
		for pt in ring:
			poly.append(Vector2(pt[0], pt[1]))
		if poly.size() >= 3:
			polygons.append(poly)

	return polygons


func _draw() -> void:
	var panel_rect := Rect2(Vector2.ZERO, size)
	draw_rect(panel_rect, Color(0.05, 0.08, 0.06, 0.72), true)
	draw_rect(panel_rect, Color(1, 1, 1, 0.35), false, 2.0)

	if _player == null:
		return

	var center := size * 0.5
	var scale_px_per_m: float = (minf(size.x, size.y) * 0.5 - 6.0) / VIEW_RADIUS_M
	var player_pos := Vector2(_player.global_position.x, _player.global_position.z)

	for poly in _water_polys:
		_draw_world_polygon(poly, player_pos, center, scale_px_per_m, Color(0.15, 0.4, 0.6, 0.9))

	for line in _paths:
		_draw_world_line(line, player_pos, center, scale_px_per_m, Color(0.75, 0.55, 0.32, 0.9), 1.5)

	for line in _roads:
		_draw_world_line(line, player_pos, center, scale_px_per_m, Color(0.9, 0.9, 0.85, 0.95), 2.5)

	_draw_player_marker(center)
	_draw_north_label(center)


func _world_to_local(
	world_xz: Vector2, player_pos: Vector2, center: Vector2, scale_px_per_m: float
) -> Vector2:
	# Nessuna rotazione: nord (= -z, vedi coords.py) e' sempre "su" sullo
	# schermo, quindi la mappa dell'offset mondo -> schermo e' diretta.
	var offset := (world_xz - player_pos) * scale_px_per_m
	return center + offset


func _draw_world_line(
	pts: PackedVector2Array, player_pos: Vector2, center: Vector2,
	scale_px_per_m: float, color: Color, width: float
) -> void:
	if pts.size() < 2:
		return
	var local_pts := PackedVector2Array()
	for p in pts:
		local_pts.append(_world_to_local(p, player_pos, center, scale_px_per_m))
	draw_polyline(local_pts, color, width, true)


func _draw_world_polygon(
	pts: PackedVector2Array, player_pos: Vector2, center: Vector2,
	scale_px_per_m: float, color: Color
) -> void:
	if pts.size() < 3:
		return
	var local_pts := PackedVector2Array()
	for p in pts:
		local_pts.append(_world_to_local(p, player_pos, center, scale_px_per_m))
	draw_colored_polygon(local_pts, color)


func _draw_player_marker(center: Vector2) -> void:
	var heading := 0.0
	if _player.camera_rig != null:
		heading = _player.camera_rig.rotation.y

	# Il giocatore guarda lungo forward = -camera_rig.basis.z (vedi
	# player.gd), che con sola rotazione Y equivale a (-sin(heading), 0,
	# -cos(heading)) in coordinate mondo (x, z). La mappa non ruota (nord
	# sempre in su) e usa la stessa corrispondenza diretta mondo->schermo
	# di _world_to_local, quindi la freccia usa lo stesso (dx, dz) mondo
	# come vettore (x, y) sullo schermo, senza conversioni ulteriori.
	var dir := Vector2(-sin(heading), -cos(heading))
	var tip := center + dir * 9.0
	var back := center - dir * 7.0
	var side := Vector2(-dir.y, dir.x) * 6.0

	var triangle := PackedVector2Array([tip, back + side, back - side])
	draw_colored_polygon(triangle, Color(0.95, 0.35, 0.15))
	draw_circle(center, 2.0, Color(1, 1, 1))


func _draw_north_label(center: Vector2) -> void:
	var font := ThemeDB.fallback_font
	var pos := Vector2(center.x - 4.0, 14.0)
	draw_string(font, pos, "N", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(1, 1, 1, 0.85))


func _gui_input(event: InputEvent) -> void:
	if _player == null:
		return
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		_teleport_to_local_point(event.position)
		accept_event()


func _teleport_to_local_point(local_pos: Vector2) -> void:
	# Inverso di _world_to_local: dal punto cliccato (in pixel, relativo al
	# riquadro della minimappa) risaliamo alla posizione nel mondo.
	var center := size * 0.5
	var scale_px_per_m: float = (minf(size.x, size.y) * 0.5 - 6.0) / VIEW_RADIUS_M
	if scale_px_per_m <= 0.0:
		return

	var player_pos := Vector2(_player.global_position.x, _player.global_position.z)
	var target := player_pos + (local_pos - center) / scale_px_per_m
	target = _nearest_free_point(target)

	_player.global_position = Vector3(target.x, _player.global_position.y, target.y)
	_player.velocity = Vector3.ZERO
	print("minimap: teletrasportato a (%.1f, %.1f)." % [target.x, target.y])


func _point_is_free(point: Vector2, polygons: Array) -> bool:
	for poly in polygons:
		if Geometry2D.is_point_in_polygon(point, poly):
			return false
	return true


func _nearest_free_point(target: Vector2) -> Vector2:
	# Se il punto cliccato cade dentro l'acqua o un edificio, cerca il punto
	# libero piu' vicino allargando la ricerca a cerchi concentrici (stessa
	# idea di _find_safe_spawn_point in world.gd, qui autonoma perche'
	# minimap.gd non ha accesso a quelle funzioni private).
	if _point_is_free(target, _water_polys) and _point_is_free(target, _building_polys):
		return target

	var per_ring := 16
	var radius := TELEPORT_SEARCH_STEP_M
	while radius <= TELEPORT_SEARCH_MAX_RADIUS_M:
		for i in per_ring:
			var angle := (TAU / per_ring) * i
			var candidate := target + Vector2(cos(angle), sin(angle)) * radius
			if _point_is_free(candidate, _water_polys) and _point_is_free(candidate, _building_polys):
				return candidate
		radius += TELEPORT_SEARCH_STEP_M

	var msg := "minimap: nessun punto libero trovato vicino al clic, "
	msg += "teletrasporto li' vicino comunque."
	push_warning(msg)
	return target
