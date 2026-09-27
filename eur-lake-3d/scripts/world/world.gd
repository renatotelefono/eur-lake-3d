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

@export var spawn_position: Vector3 = Vector3(0, 1.0, 10.0)


func _ready() -> void:
	_setup_environment()
	_load_generated_world()
	_spawn_vegetation()
	_spawn_player()


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
	# Aggiunge collisioni statiche (trimesh) a ogni mesh generata dalla
	# pipeline (terreno, edifici, strade...), cosi' il giocatore ci
	# cammina/scontra sopra senza dover pre-calcolare collider in Blender.
	for child in node.get_children():
		if child is MeshInstance3D:
			child.create_trimesh_collision()
		_add_static_collisions(child)


func _spawn_vegetation() -> void:
	var vegetation_script := load(VEGETATION_SCRIPT_PATH)
	var vegetation: Node3D = vegetation_script.new()
	vegetation.name = "VegetationSpawner"
	add_child(vegetation)


func _spawn_player() -> void:
	var player_scene: PackedScene = load(PLAYER_SCENE_PATH)
	var player := player_scene.instantiate()
	player.position = spawn_position
	add_child(player)
