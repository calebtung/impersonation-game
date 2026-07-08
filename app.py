from __future__ import annotations

import os

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room

from lobby import GameRegistry, LobbyError, Role


app = Flask(__name__)
app.config["SECRET_KEY"] = "replace-me-before-production"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
registry = GameRegistry()


@app.get("/")
def index() -> str:
	return render_template("index.html")


def _emit_error(message: str) -> None:
	emit("game_error", {"message": message})


def _broadcast_lobby_state(code: str) -> None:
	try:
		lobby = registry.get_lobby(code)
	except LobbyError:
		return

	for player in lobby.players.values():
		if player.sid:
			socketio.emit("state_update", lobby.to_client_payload(player.username), to=player.sid)


def _identity_for_request() -> tuple[str, str] | None:
	return registry.identity_for_sid(request.sid)


@socketio.on("connect")
def on_connect() -> None:
	emit("connected", {"sid": request.sid})


@socketio.on("disconnect")
def on_disconnect() -> None:
	identity = registry.unbind_sid(request.sid)
	if identity is None:
		return

	code, username = identity
	lobby = registry.lobbies.get(code)
	if lobby is None:
		return

	try:
		lobby.remove_player(username)
	except LobbyError as exc:
		if str(exc) == "HOST_DISCONNECTED":
			socketio.emit("lobby_closed", {"reason": "Host disconnected"}, room=code)
			registry.remove_lobby(code)
			return

	leave_room(code)
	if not lobby.players:
		registry.remove_lobby(code)
	else:
		_broadcast_lobby_state(code)


@socketio.on("create_lobby")
def create_lobby(data: dict) -> None:
	username = (data.get("username") or "").strip().lower()
	try:
		lobby = registry.create_lobby(username)
		registry.bind_sid(request.sid, lobby.code, username)
		join_room(lobby.code)
		_broadcast_lobby_state(lobby.code)
	except LobbyError as exc:
		_emit_error(str(exc))


@socketio.on("join_lobby")
def join_lobby_event(data: dict) -> None:
	code = (data.get("code") or "").strip().lower()
	username = (data.get("username") or "").strip().lower()
	try:
		lobby = registry.join_lobby(code, username)
		registry.bind_sid(request.sid, code, username)
		join_room(code)
		_broadcast_lobby_state(lobby.code)
	except LobbyError as exc:
		_emit_error(str(exc))


@socketio.on("leave_lobby")
def leave_lobby_event() -> None:
	identity = _identity_for_request()
	if identity is None:
		return
	code, username = identity
	registry.unbind_sid(request.sid)

	lobby = registry.lobbies.get(code)
	if lobby is None:
		return

	try:
		lobby.remove_player(username)
	except LobbyError as exc:
		if str(exc) == "HOST_DISCONNECTED":
			socketio.emit("lobby_closed", {"reason": "Host left"}, room=code)
			registry.remove_lobby(code)
			leave_room(code)
			return

	leave_room(code)
	emit("left_lobby", {})
	if not lobby.players:
		registry.remove_lobby(code)
	else:
		_broadcast_lobby_state(code)


@socketio.on("close_lobby")
def close_lobby_event() -> None:
	identity = _identity_for_request()
	if identity is None:
		return
	code, username = identity
	lobby = registry.lobbies.get(code)
	if lobby is None:
		return
	try:
		lobby.close_lobby(username)
		socketio.emit("lobby_closed", {"reason": "Host closed lobby"}, room=code)
		registry.remove_lobby(code)
	except LobbyError as exc:
		_emit_error(str(exc))


@socketio.on("assign_role")
def assign_role_event(data: dict) -> None:
	identity = _identity_for_request()
	if identity is None:
		return
	code, acting_username = identity
	target_username = (data.get("target_username") or "").strip()
	role_value = (data.get("role") or "").strip().upper()

	lobby = registry.lobbies.get(code)
	if lobby is None:
		return
	try:
		role = Role(role_value)
		lobby.assign_special_role(acting_username, target_username, role)
		_broadcast_lobby_state(code)
	except (LobbyError, ValueError) as exc:
		_emit_error(str(exc))


@socketio.on("set_questions")
def set_questions_event(data: dict) -> None:
	identity = _identity_for_request()
	if identity is None:
		return
	code, username = identity
	text = (data.get("questions_text") or "").lower()

	lobby = registry.lobbies.get(code)
	if lobby is None:
		return
	try:
		lobby.set_questions_from_text(username, text)
		_broadcast_lobby_state(code)
	except LobbyError as exc:
		_emit_error(str(exc))


@socketio.on("start_game")
def start_game_event(data: dict | None = None) -> None:
	identity = _identity_for_request()
	if identity is None:
		return
	code, username = identity
	lobby = registry.lobbies.get(code)
	if lobby is None:
		return
	try:
		questions_text = ""
		if data:
			questions_text = (data.get("questions_text") or "").lower()
		lobby.start_game(username, questions_text)
		_broadcast_lobby_state(code)
	except LobbyError as exc:
		_emit_error(str(exc))


@socketio.on("submit_answer")
def submit_answer_event(data: dict) -> None:
	identity = _identity_for_request()
	if identity is None:
		return
	code, username = identity
	answer_text = (data.get("answer") or "").lower()

	lobby = registry.lobbies.get(code)
	if lobby is None:
		return
	try:
		lobby.submit_answer(username, answer_text)
		_broadcast_lobby_state(code)
	except LobbyError as exc:
		_emit_error(str(exc))


@socketio.on("start_voting")
def start_voting_event() -> None:
	identity = _identity_for_request()
	if identity is None:
		return
	code, username = identity

	lobby = registry.lobbies.get(code)
	if lobby is None:
		return
	try:
		lobby.start_voting(username)
		_broadcast_lobby_state(code)
	except LobbyError as exc:
		_emit_error(str(exc))


@socketio.on("submit_vote")
def submit_vote_event(data: dict) -> None:
	identity = _identity_for_request()
	if identity is None:
		return
	code, username = identity
	answer_id = data.get("answer_id") or ""

	lobby = registry.lobbies.get(code)
	if lobby is None:
		return
	try:
		lobby.submit_vote(username, answer_id)
		_broadcast_lobby_state(code)
	except LobbyError as exc:
		_emit_error(str(exc))


@socketio.on("reveal_first_answer")
def reveal_first_answer_event() -> None:
	identity = _identity_for_request()
	if identity is None:
		return
	code, username = identity

	lobby = registry.lobbies.get(code)
	if lobby is None:
		return
	try:
		lobby.reveal_first_answer(username)
		_broadcast_lobby_state(code)
	except LobbyError as exc:
		_emit_error(str(exc))


@socketio.on("reveal_votes")
def reveal_votes_event() -> None:
	identity = _identity_for_request()
	if identity is None:
		return
	code, username = identity

	lobby = registry.lobbies.get(code)
	if lobby is None:
		return
	try:
		lobby.reveal_votes(username)
		_broadcast_lobby_state(code)
	except LobbyError as exc:
		_emit_error(str(exc))


@socketio.on("next_reveal_step")
def next_reveal_step_event() -> None:
	identity = _identity_for_request()
	if identity is None:
		return
	code, username = identity

	lobby = registry.lobbies.get(code)
	if lobby is None:
		return
	try:
		lobby.reveal_next_after_votes(username)
		_broadcast_lobby_state(code)
	except LobbyError as exc:
		_emit_error(str(exc))


@socketio.on("return_to_lobby")
def return_to_lobby_event() -> None:
	identity = _identity_for_request()
	if identity is None:
		return
	code, username = identity
	lobby = registry.lobbies.get(code)
	if lobby is None:
		return
	try:
		lobby.return_to_lobby(username)
		_broadcast_lobby_state(code)
	except LobbyError as exc:
		_emit_error(str(exc))


if __name__ == "__main__":
	allow_unsafe = os.getenv("IMPERSONATION_ALLOW_UNSAFE_WERKZEUG") == "1" or os.getenv("CI") == "true"
	socketio.run(
		app,
		host="0.0.0.0",
		port=5000,
		debug=True,
		use_reloader=False,
		allow_unsafe_werkzeug=allow_unsafe,
	)
