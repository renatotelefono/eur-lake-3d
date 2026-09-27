extends CharacterBody3D
## Controller del giocatore: camminata (WASD), corsa (Shift), salto (Spazio),
## telecamera in terza persona orbitale (mouse). L'intera gerarchia dei nodi
## figli (collisione, mesh, camera rig) viene creata via codice in _ready(),
## cosi' la scena .tscn resta minimale e non dipende da risorse binarie
## fragili da scrivere a mano.
##
## Tasti: WASD muove, Shift corre, Spazio salta, mouse guarda intorno,
## Esc rilascia/ricattura il mouse.

const WALK_SPEED := 4.0
const RUN_SPEED := 8.0
const JUMP_VELOCITY := 4.8
const MOUSE_SENSITIVITY := 0.0035
const PITCH_MIN := -0.7  # rad, ~-40 gradi
const PITCH_MAX := 1.2  # rad, ~70 gradi
const CAPSULE_HEIGHT := 1.8
const CAPSULE_RADIUS := 0.35
const ACCELERATION_TIME := 4.0

var camera_rig: Node3D
var spring_arm: SpringArm3D
var mesh: MeshInstance3D

var _gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity", 9.8)


func _ready() -> void:
	_build_body()
	_build_camera_rig()
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _build_body() -> void:
	var collision := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.height = CAPSULE_HEIGHT
	capsule.radius = CAPSULE_RADIUS
	collision.shape = capsule
	collision.position = Vector3(0, CAPSULE_HEIGHT * 0.5, 0)
	add_child(collision)

	mesh = MeshInstance3D.new()
	var capsule_mesh := CapsuleMesh.new()
	capsule_mesh.height = CAPSULE_HEIGHT
	capsule_mesh.radius = CAPSULE_RADIUS
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.85, 0.35, 0.2)
	capsule_mesh.material = mat
	mesh.mesh = capsule_mesh
	mesh.position = Vector3(0, CAPSULE_HEIGHT * 0.5, 0)
	add_child(mesh)


func _build_camera_rig() -> void:
	camera_rig = Node3D.new()
	camera_rig.name = "CameraRig"
	camera_rig.position = Vector3(0, CAPSULE_HEIGHT * 0.9, 0)
	add_child(camera_rig)

	spring_arm = SpringArm3D.new()
	spring_arm.name = "SpringArm"
	spring_arm.spring_length = 4.5
	spring_arm.rotation.x = deg_to_rad(-10.0)
	camera_rig.add_child(spring_arm)

	var camera := Camera3D.new()
	camera.name = "Camera3D"
	camera.current = true
	spring_arm.add_child(camera)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		camera_rig.rotation.y -= event.relative.x * MOUSE_SENSITIVITY
		spring_arm.rotation.x = clamp(
			spring_arm.rotation.x - event.relative.y * MOUSE_SENSITIVITY,
			PITCH_MIN, PITCH_MAX
		)
	if event.is_action_pressed("ui_cancel"):
		if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
			Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		else:
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= _gravity * delta
	elif Input.is_action_just_pressed("jump"):
		velocity.y = JUMP_VELOCITY

	var input_dir := Vector2.ZERO
	if Input.is_action_pressed("move_forward"):
		input_dir.y += 1.0
	if Input.is_action_pressed("move_back"):
		input_dir.y -= 1.0
	if Input.is_action_pressed("move_right"):
		input_dir.x += 1.0
	if Input.is_action_pressed("move_left"):
		input_dir.x -= 1.0
	if input_dir.length() > 1.0:
		input_dir = input_dir.normalized()

	var forward := -camera_rig.global_transform.basis.z
	var right := camera_rig.global_transform.basis.x
	forward.y = 0.0
	right.y = 0.0
	forward = forward.normalized()
	right = right.normalized()

	var move_dir := right * input_dir.x + forward * input_dir.y
	var speed := RUN_SPEED if Input.is_action_pressed("run") else WALK_SPEED

	if move_dir.length() > 0.001:
		move_dir = move_dir.normalized()
		velocity.x = move_dir.x * speed
		velocity.z = move_dir.z * speed
		var target_angle := atan2(move_dir.x, move_dir.z)
		mesh.rotation.y = lerp_angle(mesh.rotation.y, target_angle, ACCELERATION_TIME * delta)
	else:
		velocity.x = move_toward(velocity.x, 0.0, speed * ACCELERATION_TIME * delta)
		velocity.z = move_toward(velocity.z, 0.0, speed * ACCELERATION_TIME * delta)

	move_and_slide()
