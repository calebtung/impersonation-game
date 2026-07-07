import unittest

from lobby import GameRegistry, Lobby, LobbyError, Phase, Role, TargetKind


class LobbyFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.lobby = Lobby(code="1234", host_username="Host_01")
        self.lobby.add_player("Alice")
        self.lobby.add_player("Bob")
        self.lobby.add_player("Cara")

    def test_unique_bride_and_groom_assignment_replaces_previous_holder(self):
        self.lobby.assign_special_role("Host_01", "Alice", Role.BRIDE)
        self.assertEqual(self.lobby.get_player("Alice").role, Role.BRIDE)

        self.lobby.assign_special_role("Host_01", "Bob", Role.BRIDE)
        self.assertEqual(self.lobby.get_player("Bob").role, Role.BRIDE)
        self.assertEqual(self.lobby.get_player("Alice").role, Role.FRIEND)

        self.lobby.assign_special_role("Host_01", "Cara", Role.GROOM)
        self.assertEqual(self.lobby.get_player("Cara").role, Role.GROOM)

    def test_only_host_can_assign_roles(self):
        with self.assertRaisesRegex(LobbyError, "Only HOST can assign roles"):
            self.lobby.assign_special_role("Alice", "Bob", Role.BRIDE)

    def test_start_game_requires_questions(self):
        with self.assertRaisesRegex(LobbyError, "Please add questions before starting"):
            self.lobby.start_game("Host_01")

    def test_set_questions_parses_non_empty_lines(self):
        raw = "  First?  \n\nSecond?\n   \nThird?  "
        self.lobby.set_questions_from_text("Host_01", raw)
        self.assertEqual(self.lobby.questions_list, ["First?", "Second?", "Third?"])

    def test_full_round_transitions_to_finish_and_populates_leaderboards(self):
        self.lobby.assign_special_role("Host_01", "Alice", Role.BRIDE)
        self.lobby.assign_special_role("Host_01", "Bob", Role.GROOM)

        self.lobby.start_game("Host_01", "Best wedding memory?")
        self.assertEqual(self.lobby.phase, Phase.QUESTION)

        self.lobby.submit_answer("Host_01", "When the cake survived")
        self.lobby.submit_answer("Alice", "First dance")
        self.lobby.submit_answer("Bob", "Ring entrance")
        self.lobby.submit_answer("Cara", "Late-night tacos")

        self.assertTrue(self.lobby.is_everyone_answered())
        self.lobby.start_voting("Host_01")
        self.assertEqual(self.lobby.phase, Phase.VOTING)

        answers = {a.username: a.answer_id for a in self.lobby.current_round.answers}
        self.lobby.submit_vote("Host_01", answers["Alice"])
        self.lobby.submit_vote("Alice", answers["Alice"])
        self.lobby.submit_vote("Bob", answers["Alice"])
        self.lobby.submit_vote("Cara", answers["Bob"])

        self.assertTrue(self.lobby.is_everyone_voted())
        self.lobby.reveal_first_answer("Host_01")
        self.assertEqual(self.lobby.phase, Phase.REVEAL_ANSWER)
        self.assertEqual(self.lobby.current_round.reveal_target, TargetKind.FRIEND_BLOCK)

        # Reveal each HOST/FRIEND answer: REVEAL_ANSWER -> REVEAL_VOTES -> next
        while self.lobby.current_round.reveal_target == TargetKind.FRIEND_BLOCK:
            self.lobby.reveal_votes("Host_01")
            self.assertEqual(self.lobby.phase, Phase.REVEAL_VOTES)
            self.lobby.reveal_next_after_votes("Host_01")

        self.assertEqual(self.lobby.phase, Phase.REVEAL_ANSWER)
        self.assertEqual(self.lobby.current_round.reveal_target, TargetKind.BRIDE)

        # Bride reveal -> votes -> groom reveal
        self.lobby.reveal_votes("Host_01")
        self.lobby.reveal_next_after_votes("Host_01")
        self.assertEqual(self.lobby.phase, Phase.REVEAL_ANSWER)
        self.assertEqual(self.lobby.current_round.reveal_target, TargetKind.GROOM)

        # Groom reveal -> votes -> finalize round -> finish
        self.lobby.reveal_votes("Host_01")
        self.lobby.reveal_next_after_votes("Host_01")

        self.assertEqual(self.lobby.phase, Phase.FINISH)
        boards = self.lobby.leaderboard_payload()
        self.assertEqual(boards["most_votes"][0], ("Alice", 3))
        self.assertEqual(dict(boards["voted_bride_most"]), {"Host_01": 1, "Alice": 1, "Bob": 1})
        self.assertEqual(dict(boards["voted_groom_most"]), {"Cara": 1})
        self.assertEqual(boards["bride_groom_agreement"]["agreed"], 1)
        self.assertEqual(boards["bride_groom_agreement"]["total_questions"], 1)

    def test_host_and_friend_cannot_vote_own_answer(self):
        self.lobby.start_game("Host_01", "Q1")
        self.lobby.submit_answer("Host_01", "Host answer")
        self.lobby.submit_answer("Alice", "A")
        self.lobby.submit_answer("Bob", "B")
        self.lobby.submit_answer("Cara", "C")
        self.lobby.start_voting("Host_01")

        answers = {a.username: a.answer_id for a in self.lobby.current_round.answers}

        with self.assertRaisesRegex(LobbyError, "cannot vote for your own answer"):
            self.lobby.submit_vote("Host_01", answers["Host_01"])

        with self.assertRaisesRegex(LobbyError, "cannot vote for your own answer"):
            self.lobby.submit_vote("Alice", answers["Alice"])

    def test_bride_and_groom_can_vote_own_answer(self):
        self.lobby.assign_special_role("Host_01", "Alice", Role.BRIDE)
        self.lobby.assign_special_role("Host_01", "Bob", Role.GROOM)
        self.lobby.start_game("Host_01", "Q1")

        self.lobby.submit_answer("Host_01", "Host answer")
        self.lobby.submit_answer("Alice", "Bride answer")
        self.lobby.submit_answer("Bob", "Groom answer")
        self.lobby.submit_answer("Cara", "Friend answer")
        self.lobby.start_voting("Host_01")

        answers = {a.username: a.answer_id for a in self.lobby.current_round.answers}
        self.lobby.submit_vote("Alice", answers["Alice"])
        self.lobby.submit_vote("Bob", answers["Bob"])

        self.assertEqual(self.lobby.submitted_votes_count(), 2)

    def test_to_client_payload_exposes_host_buttons_readiness_flags(self):
        self.lobby.start_game("Host_01", "Q1")
        self.lobby.submit_answer("Host_01", "Host")
        self.lobby.submit_answer("Alice", "A")
        self.lobby.submit_answer("Bob", "B")

        # Cara has not answered yet
        host_payload = self.lobby.to_client_payload("Host_01")
        self.assertFalse(host_payload["host_can_start_voting"])

        self.lobby.submit_answer("Cara", "C")
        host_payload = self.lobby.to_client_payload("Host_01")
        self.assertTrue(host_payload["host_can_start_voting"])

        self.lobby.start_voting("Host_01")
        answers = {a.username: a.answer_id for a in self.lobby.current_round.answers}
        self.lobby.submit_vote("Host_01", answers["Alice"])
        self.lobby.submit_vote("Alice", answers["Bob"])
        self.lobby.submit_vote("Bob", answers["Alice"])

        host_payload = self.lobby.to_client_payload("Host_01")
        self.assertFalse(host_payload["host_can_reveal_first"])

        self.lobby.submit_vote("Cara", answers["Alice"])
        host_payload = self.lobby.to_client_payload("Host_01")
        self.assertTrue(host_payload["host_can_reveal_first"])


class GameRegistryTestCase(unittest.TestCase):
    def test_create_and_join_lobby_validation(self):
        registry = GameRegistry()

        with self.assertRaisesRegex(LobbyError, "Username must be"):
            registry.create_lobby("x")

        lobby = registry.create_lobby("Host_01")
        self.assertEqual(len(lobby.code), 4)
        self.assertTrue(lobby.code.isdigit())

        with self.assertRaisesRegex(LobbyError, "No lobby found"):
            registry.join_lobby("9999", "Guest")

        joined = registry.join_lobby(lobby.code, "Guest_1")
        self.assertEqual(joined.code, lobby.code)

    def test_sid_binding_and_unbinding(self):
        registry = GameRegistry()
        lobby = registry.create_lobby("Host_01")

        registry.bind_sid("sid-host", lobby.code, "Host_01")
        self.assertEqual(registry.identity_for_sid("sid-host"), (lobby.code, "Host_01"))
        self.assertEqual(lobby.get_player("Host_01").sid, "sid-host")

        identity = registry.unbind_sid("sid-host")
        self.assertEqual(identity, (lobby.code, "Host_01"))
        self.assertIsNone(registry.identity_for_sid("sid-host"))
        self.assertIsNone(lobby.get_player("Host_01").sid)


if __name__ == "__main__":
    unittest.main()
