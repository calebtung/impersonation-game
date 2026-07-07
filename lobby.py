from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{2,20}$")


class Role(str, Enum):
	HOST = "HOST"
	BRIDE = "BRIDE"
	GROOM = "GROOM"
	FRIEND = "FRIEND"


class Phase(str, Enum):
	LOBBY = "LOBBY"
	QUESTION = "QUESTION"
	VOTING = "VOTING"
	REVEAL_ANSWER = "REVEAL_ANSWER"
	REVEAL_VOTES = "REVEAL_VOTES"
	FINISH = "FINISH"


class TargetKind(str, Enum):
	FRIEND_BLOCK = "FRIEND_BLOCK"
	BRIDE = "BRIDE"
	GROOM = "GROOM"


@dataclass
class Player:
	username: str
	role: Role
	sid: str | None = None


@dataclass
class AnswerEntry:
	answer_id: str
	username: str
	role: Role
	text: str


@dataclass
class RoundState:
	question_index: int
	question_text: str
	answers: list[AnswerEntry] = field(default_factory=list)
	votes: dict[str, str] = field(default_factory=dict)
	reveal_target: TargetKind = TargetKind.FRIEND_BLOCK
	reveal_friend_index: int = 0


def role_sort_key(role: Role) -> int:
	if role == Role.HOST:
		return 0
	if role == Role.FRIEND:
		return 1
	if role == Role.BRIDE:
		return 2
	return 3


def is_username_valid(username: str) -> bool:
	return bool(USERNAME_RE.fullmatch(username))


class LobbyError(Exception):
	pass


class Lobby:
	def __init__(self, code: str, host_username: str):
		self.code = code
		self.host_username = host_username
		self.players: dict[str, Player] = {
			host_username: Player(username=host_username, role=Role.HOST)
		}
		self.phase: Phase = Phase.LOBBY
		self.questions_list: list[str] = []
		self.answers_dict: dict[int, list[dict[str, Any]]] = {}
		self.current_round: RoundState | None = None
		self.current_question_index = -1

		self.total_votes_received: Counter[str] = Counter()
		self.voted_bride_count: Counter[str] = Counter()
		self.voted_groom_count: Counter[str] = Counter()
		self.bride_groom_agreement = 0

	def get_player(self, username: str) -> Player:
		if username not in self.players:
			raise LobbyError("Player not found in lobby")
		return self.players[username]

	def get_sorted_players(self) -> list[Player]:
		host = [self.players[self.host_username]] if self.host_username in self.players else []
		others = [p for n, p in self.players.items() if n != self.host_username]
		others.sort(key=lambda p: p.username.lower())
		return host + others

	def add_player(self, username: str) -> None:
		if self.phase != Phase.LOBBY:
			raise LobbyError("Game already started")
		if username in self.players:
			raise LobbyError("Username already taken inside your desired lobby")
		self.players[username] = Player(username=username, role=Role.FRIEND)

	def remove_player(self, username: str) -> None:
		if username not in self.players:
			return
		del self.players[username]
		if not self.players:
			return
		if self.host_username == username:
			raise LobbyError("HOST_DISCONNECTED")

	def assign_special_role(self, acting_username: str, target_username: str, role: Role) -> None:
		if acting_username != self.host_username:
			raise LobbyError("Only HOST can assign roles")
		if role not in {Role.BRIDE, Role.GROOM, Role.FRIEND}:
			raise LobbyError("Invalid role assignment")
		if target_username not in self.players:
			raise LobbyError("Target user not found")
		if target_username == self.host_username:
			raise LobbyError("HOST role cannot be reassigned")

		if role in {Role.BRIDE, Role.GROOM}:
			for player in self.players.values():
				if player.role == role:
					player.role = Role.FRIEND

		self.players[target_username].role = role

	def set_questions_from_text(self, acting_username: str, raw_text: str) -> None:
		if acting_username != self.host_username:
			raise LobbyError("Only HOST can set questions")
		questions = [line.strip() for line in raw_text.splitlines() if line.strip()]
		if not questions:
			raise LobbyError("Please provide at least one question")
		self.questions_list = questions

	def start_game(self, acting_username: str, raw_questions_text: str | None = None) -> None:
		if acting_username != self.host_username:
			raise LobbyError("Only HOST can start game")
		if raw_questions_text is not None:
			self.set_questions_from_text(acting_username, raw_questions_text)
		if not self.questions_list:
			raise LobbyError("Please add questions before starting")
		self.current_question_index = 0
		self.phase = Phase.QUESTION
		self.current_round = RoundState(
			question_index=self.current_question_index,
			question_text=self.questions_list[self.current_question_index],
		)

	def submit_answer(self, username: str, answer_text: str) -> None:
		if self.phase != Phase.QUESTION or self.current_round is None:
			raise LobbyError("Not in question state")
		answer_text = answer_text.strip()
		if not answer_text:
			raise LobbyError("Answer is required")
		if any(a.username == username for a in self.current_round.answers):
			raise LobbyError("Answer already submitted")
		role = self.get_player(username).role
		answer_id = f"Q{self.current_round.question_index}_A{len(self.current_round.answers) + 1}"
		self.current_round.answers.append(
			AnswerEntry(answer_id=answer_id, username=username, role=role, text=answer_text)
		)

	def submitted_answers_count(self) -> int:
		if self.current_round is None:
			return 0
		return len(self.current_round.answers)

	def is_everyone_answered(self) -> bool:
		return self.submitted_answers_count() == len(self.players)

	def start_voting(self, acting_username: str) -> None:
		if acting_username != self.host_username:
			raise LobbyError("Only HOST can start voting")
		if self.phase != Phase.QUESTION or self.current_round is None:
			raise LobbyError("Not in question state")
		if not self.is_everyone_answered():
			raise LobbyError("Cannot start voting until all answers are submitted")

		self.current_round.answers.sort(key=lambda a: (role_sort_key(a.role), a.username.lower()))
		self.answers_dict[self.current_round.question_index] = [
			{
				"answer_id": a.answer_id,
				"username": a.username,
				"role": a.role.value,
				"text": a.text,
				"voted_by": [],
			}
			for a in self.current_round.answers
		]
		self.phase = Phase.VOTING

	def submit_vote(self, username: str, answer_id: str) -> None:
		if self.phase != Phase.VOTING or self.current_round is None:
			raise LobbyError("Not in voting state")
		if username in self.current_round.votes:
			raise LobbyError("Vote already submitted")

		voter = self.get_player(username)
		selected = next((a for a in self.current_round.answers if a.answer_id == answer_id), None)
		if selected is None:
			raise LobbyError("Invalid answer selected")

		if voter.role in {Role.HOST, Role.FRIEND} and selected.username == username:
			raise LobbyError("You cannot vote for your own answer")

		self.current_round.votes[username] = answer_id

	def submitted_votes_count(self) -> int:
		if self.current_round is None:
			return 0
		return len(self.current_round.votes)

	def is_everyone_voted(self) -> bool:
		return self.submitted_votes_count() == len(self.players)

	def reveal_first_answer(self, acting_username: str) -> None:
		if acting_username != self.host_username:
			raise LobbyError("Only HOST can reveal answers")
		if self.phase != Phase.VOTING:
			raise LobbyError("Not in voting state")
		if not self.is_everyone_voted():
			raise LobbyError("Cannot reveal until all votes are submitted")
		if self.current_round is None:
			raise LobbyError("Round missing")

		self.current_round.reveal_target = TargetKind.FRIEND_BLOCK
		self.current_round.reveal_friend_index = 0
		self.phase = Phase.REVEAL_ANSWER

	def reveal_votes(self, acting_username: str) -> None:
		if acting_username != self.host_username:
			raise LobbyError("Only HOST can reveal votes")
		if self.phase != Phase.REVEAL_ANSWER:
			raise LobbyError("Reveal votes only from reveal-answer state")
		self.phase = Phase.REVEAL_VOTES

	def reveal_next_after_votes(self, acting_username: str) -> None:
		if acting_username != self.host_username:
			raise LobbyError("Only HOST can continue reveal")
		if self.phase != Phase.REVEAL_VOTES or self.current_round is None:
			raise LobbyError("Not in reveal-votes state")

		if self.current_round.reveal_target == TargetKind.FRIEND_BLOCK:
			self.current_round.reveal_friend_index += 1
			if self.current_round.reveal_friend_index < len(self.friend_block_answers()):
				self.phase = Phase.REVEAL_ANSWER
				return
			self.current_round.reveal_target = TargetKind.BRIDE
			self.phase = Phase.REVEAL_ANSWER
			return

		if self.current_round.reveal_target == TargetKind.BRIDE:
			self.current_round.reveal_target = TargetKind.GROOM
			self.phase = Phase.REVEAL_ANSWER
			return

		self._finalize_current_round_stats()
		if self.current_question_index + 1 < len(self.questions_list):
			self.current_question_index += 1
			self.current_round = RoundState(
				question_index=self.current_question_index,
				question_text=self.questions_list[self.current_question_index],
			)
			self.phase = Phase.QUESTION
		else:
			self.current_round = None
			self.phase = Phase.FINISH

	def return_to_lobby(self, acting_username: str) -> None:
		if acting_username != self.host_username:
			raise LobbyError("Only HOST can return to lobby")
		self.phase = Phase.LOBBY
		self.questions_list = []
		self.answers_dict = {}
		self.current_round = None
		self.current_question_index = -1
		self.total_votes_received.clear()
		self.voted_bride_count.clear()
		self.voted_groom_count.clear()
		self.bride_groom_agreement = 0

	def close_lobby(self, acting_username: str) -> None:
		if acting_username != self.host_username:
			raise LobbyError("Only HOST can close lobby")

	def friend_block_answers(self) -> list[AnswerEntry]:
		if self.current_round is None:
			return []
		return [a for a in self.current_round.answers if a.role in {Role.HOST, Role.FRIEND}]

	def bride_answer(self) -> AnswerEntry | None:
		if self.current_round is None:
			return None
		return next((a for a in self.current_round.answers if a.role == Role.BRIDE), None)

	def groom_answer(self) -> AnswerEntry | None:
		if self.current_round is None:
			return None
		return next((a for a in self.current_round.answers if a.role == Role.GROOM), None)

	def get_current_reveal_answer(self) -> AnswerEntry | None:
		if self.current_round is None:
			return None
		if self.current_round.reveal_target == TargetKind.FRIEND_BLOCK:
			friends = self.friend_block_answers()
			if self.current_round.reveal_friend_index < len(friends):
				return friends[self.current_round.reveal_friend_index]
			return None
		if self.current_round.reveal_target == TargetKind.BRIDE:
			return self.bride_answer()
		return self.groom_answer()

	def _finalize_current_round_stats(self) -> None:
		if self.current_round is None:
			return

		answer_by_id = {a.answer_id: a for a in self.current_round.answers}
		for voter, answer_id in self.current_round.votes.items():
			answer = answer_by_id.get(answer_id)
			if answer is None:
				continue
			self.total_votes_received[answer.username] += 1
			if answer.role == Role.BRIDE:
				self.voted_bride_count[voter] += 1
			if answer.role == Role.GROOM:
				self.voted_groom_count[voter] += 1

		bride_username = next((p.username for p in self.players.values() if p.role == Role.BRIDE), None)
		groom_username = next((p.username for p in self.players.values() if p.role == Role.GROOM), None)
		if bride_username and groom_username:
			bride_vote = self.current_round.votes.get(bride_username)
			groom_vote = self.current_round.votes.get(groom_username)
			if bride_vote and groom_vote and bride_vote == groom_vote:
				self.bride_groom_agreement += 1

		stored = self.answers_dict.get(self.current_round.question_index, [])
		voters_by_answer: dict[str, list[str]] = {a["answer_id"]: [] for a in stored}
		for voter, answer_id in self.current_round.votes.items():
			if answer_id in voters_by_answer:
				voters_by_answer[answer_id].append(voter)
		for entry in stored:
			entry["voted_by"] = sorted(voters_by_answer.get(entry["answer_id"], []), key=str.lower)

	def player_ui_state(self, username: str) -> str:
		role = self.get_player(username).role
		prefix = "HOST" if role == Role.HOST else role.value
		if role == Role.FRIEND:
			prefix = "FRIEND"

		if self.phase == Phase.LOBBY:
			return "HOSTLOBBY" if role == Role.HOST else "EVERYONELOBBY"
		if self.phase == Phase.QUESTION:
			return f"{prefix}GAMEQUESTION"
		if self.phase == Phase.VOTING:
			return f"{prefix}GAMEVOTING"
		if self.phase == Phase.REVEAL_ANSWER:
			if self.current_round is None:
				return f"{prefix}GAMEQUESTION"
			if self.current_round.reveal_target == TargetKind.FRIEND_BLOCK:
				return f"{prefix}GAMEREVEAL"
			if self.current_round.reveal_target == TargetKind.BRIDE:
				return f"{prefix}GAMEREVEALBRIDE"
			return f"{prefix}GAMEREVEALGROOM"
		if self.phase == Phase.REVEAL_VOTES:
			if self.current_round is None:
				return f"{prefix}GAMEQUESTION"
			if self.current_round.reveal_target == TargetKind.FRIEND_BLOCK:
				return f"{prefix}GAMEREVEALVOTE"
			if self.current_round.reveal_target == TargetKind.BRIDE:
				return f"{prefix}GAMEREVEALVOTEBRIDE"
			return f"{prefix}GAMEREVEALVOTEGROOM"
		return f"{prefix}FINISH"

	def leaderboard_payload(self) -> dict[str, Any]:
		return {
			"most_votes": sorted(self.total_votes_received.items(), key=lambda t: (-t[1], t[0].lower())),
			"voted_bride_most": sorted(self.voted_bride_count.items(), key=lambda t: (-t[1], t[0].lower())),
			"voted_groom_most": sorted(self.voted_groom_count.items(), key=lambda t: (-t[1], t[0].lower())),
			"bride_groom_agreement": {
				"agreed": self.bride_groom_agreement,
				"total_questions": len(self.questions_list),
			},
		}

	def to_client_payload(self, username: str) -> dict[str, Any]:
		player = self.get_player(username)
		current_answer = self.get_current_reveal_answer()
		current_round_votes = self.current_round.votes if self.current_round is not None else {}
		live_voters_by_answer: dict[str, list[str]] = {}
		for voter, answer_id in current_round_votes.items():
			live_voters_by_answer.setdefault(answer_id, []).append(voter)
		for voters in live_voters_by_answer.values():
			voters.sort(key=str.lower)

		vote_visibility: list[dict[str, Any]] = []
		if self.current_round is not None:
			saved_answers = self.answers_dict.get(self.current_round.question_index, [])
			for entry in saved_answers:
				masked_text = entry["text"]
				if self.phase == Phase.VOTING:
					masked_text = entry["text"]
				is_own = entry["username"] == username
				vote_visibility.append(
					{
						"answer_id": entry["answer_id"],
						"text": masked_text,
						"is_own": is_own,
						"author_username": entry["username"] if self.phase in {Phase.REVEAL_ANSWER, Phase.REVEAL_VOTES, Phase.FINISH} else None,
						"author_role": entry["role"] if self.phase in {Phase.REVEAL_ANSWER, Phase.REVEAL_VOTES, Phase.FINISH} else None,
						"voted_by": (
							live_voters_by_answer.get(entry["answer_id"], [])
							if self.phase == Phase.REVEAL_VOTES
							else []
						),
					}
				)

		submitted_answers = []
		if self.current_round is not None:
			submitted_answers = [a.username for a in self.current_round.answers]

		return {
			"lobby_code": self.code,
			"username": username,
			"role": player.role.value,
			"ui_state": self.player_ui_state(username),
			"phase": self.phase.value,
			"host_username": self.host_username,
			"players": [
				{
					"username": p.username,
					"role": p.role.value,
					"is_host": p.username == self.host_username,
				}
				for p in self.get_sorted_players()
			],
			"question_index": self.current_question_index,
			"question_total": len(self.questions_list),
			"current_question": self.current_round.question_text if self.current_round else None,
			"submitted_answers_count": len(submitted_answers),
			"submitted_votes_count": self.submitted_votes_count(),
			"player_count": len(self.players),
			"player_has_answered": username in submitted_answers,
			"player_has_voted": username in (self.current_round.votes if self.current_round else {}),
			"answers_for_voting": vote_visibility,
			"current_reveal_answer": {
				"answer_id": current_answer.answer_id,
				"text": current_answer.text,
				"username": current_answer.username,
				"role": current_answer.role.value,
			}
			if current_answer
			else None,
			"host_can_start_voting": self.phase == Phase.QUESTION and self.is_everyone_answered() and username == self.host_username,
			"host_can_reveal_first": self.phase == Phase.VOTING and self.is_everyone_voted() and username == self.host_username,
			"leaderboards": self.leaderboard_payload() if self.phase == Phase.FINISH else None,
		}


class GameRegistry:
	def __init__(self) -> None:
		self.lobbies: dict[str, Lobby] = {}
		self.sid_to_identity: dict[str, tuple[str, str]] = {}

	def _generate_code(self) -> str:
		for _ in range(2000):
			code = f"{random.randint(0, 9999):04d}"
			if code not in self.lobbies:
				return code
		raise LobbyError("Unable to create lobby code")

	def create_lobby(self, username: str) -> Lobby:
		if not is_username_valid(username):
			raise LobbyError("Username must be 2-20 characters, letters/numbers/underscore")
		code = self._generate_code()
		lobby = Lobby(code=code, host_username=username)
		self.lobbies[code] = lobby
		return lobby

	def get_lobby(self, code: str) -> Lobby:
		lobby = self.lobbies.get(code)
		if lobby is None:
			raise LobbyError("No lobby found to match desired Lobby Code")
		return lobby

	def join_lobby(self, code: str, username: str) -> Lobby:
		if not is_username_valid(username):
			raise LobbyError("Username must be 2-20 characters, letters/numbers/underscore")
		lobby = self.get_lobby(code)
		lobby.add_player(username)
		return lobby

	def remove_lobby(self, code: str) -> None:
		self.lobbies.pop(code, None)

	def bind_sid(self, sid: str, code: str, username: str) -> None:
		self.sid_to_identity[sid] = (code, username)
		lobby = self.get_lobby(code)
		lobby.get_player(username).sid = sid

	def unbind_sid(self, sid: str) -> tuple[str, str] | None:
		identity = self.sid_to_identity.pop(sid, None)
		if identity is None:
			return None
		code, username = identity
		lobby = self.lobbies.get(code)
		if lobby and username in lobby.players:
			lobby.players[username].sid = None
		return identity

	def identity_for_sid(self, sid: str) -> tuple[str, str] | None:
		return self.sid_to_identity.get(sid)
