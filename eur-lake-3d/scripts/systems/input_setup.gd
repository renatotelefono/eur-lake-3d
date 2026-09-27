extends Node
## Autoload (vedi project.godot, sezione [autoload]) che registra a runtime
## le InputMap actions usate dal gioco. Evitiamo di scrivere a mano le
## risorse InputEventKey dentro project.godot: e' un formato facile da
## corrompere senza l'editor, mentre InputMap via codice e' esplicito,
## leggibile e facile da estendere (es. supporto controller in futuro).

func _ready() -> void:
	_ensure_key_action("move_forward", KEY_W)
	_ensure_key_action("move_back", KEY_S)
	_ensure_key_action("move_left", KEY_A)
	_ensure_key_action("move_right", KEY_D)
	_ensure_key_action("jump", KEY_SPACE)
	_ensure_key_action("run", KEY_SHIFT)


func _ensure_key_action(action_name: String, keycode: Key) -> void:
	if not InputMap.has_action(action_name):
		InputMap.add_action(action_name)

	var event := InputEventKey.new()
	event.physical_keycode = keycode
	InputMap.action_add_event(action_name, event)
