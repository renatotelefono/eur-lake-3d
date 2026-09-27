extends Node3D
## Root della scena di gioco (scenes/world/eur_world.tscn). Crea a runtime
## illuminazione/cielo, carica il mondo generato dalla pipeline
## OSM -> Blender (assets/generated/eur_world.glb), aggiunge le collisioni,
## istanzia la vegetazione procedurale e il giocatore.
##
## Se assets/generated/eur_world.glb non esiste ancora (perche' la pipeline
## non e' stata eseguita), la scena si apre comunque: mostra solo cielo,
## luce e il giocatore su un piano vuoto, con un avviso in console.

const WORLD_GLB_PATH := "res://assets/generated/eur_world.glb"
const PLAYER_SCENE_PATH := "res://scenes/player/player.tscn"
const VEGETATION_SCRIPT_PATH := "res://scripts/systems/vegetation_scatter.gd"
const STREET_HUD_SCRIPT_PATH := "res://scripts/systems/street_hud.gd"
const WATER_GEOJSON_PATH := "res://data/osm/water.geojson"
const BUILDINGS_GEOJSON_PATH := "res://data/osm/buildings.geojson"

# Solo questi prefissi di nome ricevono collisione fisica: edifici e terreno.
# Strade/sentieri/acqua/aree verdi restano puramente visivi (il terreno sotto
# di loro fornisce gia' la superficie calpestabile) - averli tutti solidi
# causava sovrapposizioni di collisioni vicino al lago che incastravano il
# giocatore impedendogli di muoversi.
const COLLIDABLE_PREFIXES := ["building_", "ground"]

# Punto di partenza "preferito" (vicino al centro/origine dell'area). Se
# cade dentro l'acqua o dentro un edificio, _find_safe_spawn_point() cerca
# automaticamente il punto libero piu' vicino, cosi' non serve aggiustarlo
# a mano ogni volta che si scaricano dati OSM diversi/aggiornati.
@export var spawn_position: Vector3 = Vector3(0, 1.0, 10.0)


func _ready() -> void:
	_setup_environment()
	_load_generated_world()
	_spawn_vegetation()
	spawn_position = _find_safe_spawn_point()
	var player := _spawn_player()
	_spawn_street_hud(player)


func _setup_environment() -> void:
	var sun := DirectionalLight3D.new()
	sun.name = "Sun"
	sun.rotation_degrees = Vector3(-50, -30, 0)
	sun.light_energy = 1.1
	sun.shadow_enabled = true
	add_child(sun)

	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color(0.38, 0.58, 0.92)
	sky_material.sky_horizon_color = Color(0.75, 0.83, 0.93)
	sky_material.ground_bottom_color = Color(0.3, 0.28, 0.25)
	sky_material.ground_horizon_color = Color(0.75, 0.83, 0.93)

	var sky := Sky.new()
	sky.sky_material = sky_material

	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = 1.0
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC

	var world_env := WorldEnvironment.new()
	world_env.name = "WorldEnvironment"
	world_env.environment = env
	add_child(world_env)


func _load_generated_world() -> void:
	if not ResourceLoader.exists(WORLD_GLB_PATH):
		var msg := "world.gd: %s non trovato. Esegui la pipeline " % WORLD_GLB_PATH
		msg += "(pipeline/fetch_osm.py e poi pipeline/blender_import.py) "
		msg += "per generare il mondo, poi riapri il progetto in Godot."
		push_warning(msg)
		return

	var packed: PackedScene = load(WORLD_GLB_PATH)
	if packed == null:
		push_warning("world.gd: impossibile caricare %s" % WORLD_GLB_PATH)
		return

	var instance := packed.instantiate()
	instance.name = "GeneratedWorld"
	add_child(instance)

	_add_static_collisions(instance)


func _add_static_collisions(node: Node) -> void:
	for child in node.get_children():
		if child is MeshInstance3D and _is_collidable(child.name):
			child.create_trimesh_collision()
		_add_static_collisions(child)


func _is_collidable(node_name: String) -> bool:
	for prefix in COLLIDABLE_PREFIXES:
		if node_name.begins_with(prefix):
			return true
	return false


func _find_safe_spawn_point() -> Vector3:
	# Cerca un punto di spawn che non cada dentro l'acqua o dentro un
	# edificio, partendo dal punto preferito (spawn_position) e allargando
	# la ricerca a cerchi concentrici. Se i GeoJSON non sono disponibili
	# (es. pipeline non ancora eseguita), usa semplicemente il default.
	var water_polys := _load_polygons(WATER_GEOJSON_PATH)
	var building_polys := _load_polygons(BUILDINGS_GEOJSON_PATH)

	if water_polys.is_empty() and building_polys.is_empty():
		return spawn_position

	var start := Vector2(spawn_position.x, spawn_position.z)
	for candidate in _spiral_candidates(start, 3.0, 16, 300.0):
		if _point_is_free(candidate, water_polys) and _point_is_free(candidate, building_polys):
			return Vector3(candidate.x, spawn_position.y, candidate.y)

	var msg := "world.gd: nessun punto di spawn libero trovato entro il raggio "
	msg += "di ricerca, uso il default."
	push_warning(msg)
	return spawn_position


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


func _point_is_free(point: Vector2, polygons: Array) -> bool:
	for poly in polygons:
		if Geometry2D.is_point_in_polygon(point, poly):
			return false
	return true


func _spiral_candidates(center: Vector2, step: float, per_ring: int, max_radius: float) -> Array:
	var points: Array = [center]
	var radius := step
	while radius <= max_radius:
		for i in per_ring:
			var angle := (TAU / per_ring) * i
			points.append(center + Vector2(cos(angle), sin(angle)) * radius)
		radius += step
	return points


func _spawn_vegetation() -> void:
	var vegetation_script := load(VEGETATION_SCRIPT_PATH)
	var vegetation: Node3D = vegetation_script.new()
	vegetation.name = "VegetationSpawner"
	add_child(vegetation)


func _spawn_player() -> Node3D:
	var player_scene: PackedScene = load(PLAYER_SCENE_PATH)
	var player := player_scene.instantiate()
	player.position = spawn_position
	add_child(player)
	return player


func _spawn_street_hud(player: Node3D) -> void:
	var hud_script := load(STREET_HUD_SCRIPT_PATH)
	var hud: Node = hud_script.new()
	hud.name = "StreetHud"
	add_child(hud)
	hud.setup(player)