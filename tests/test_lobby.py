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

    def test_start_game_requires_bride_and_groom_assignments(self):
        with self.assertRaisesRegex(LobbyError, "Please assign BRIDE and GROOM before starting"):
            self.lobby.start_game("Host_01", "Q1")

        self.lobby.assign_special_role("Host_01", "Alice", Role.BRIDE)
        with self.assertRaisesRegex(LobbyError, "Please assign BRIDE and GROOM before starting"):
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

        options = {
            a["text"]: a["answer_id"]
            for a in self.lobby.to_client_payload("Host_01")["answers_for_voting"]
        }
        self.lobby.submit_vote("Host_01", options["First dance"])
        self.lobby.submit_vote("Alice", options["First dance"])
        self.lobby.submit_vote("Bob", options["First dance"])
        self.lobby.submit_vote("Cara", options["Ring entrance"])

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
        self.assertEqual(dict(boards["voted_groom_most"]), {"Host_01": 1, "Alice": 1, "Bob": 1})
        self.assertEqual(boards["bride_groom_agreement"]["agreed"], 1)
        self.assertEqual(boards["bride_groom_agreement"]["total_questions"], 1)

    def test_voted_with_counts_use_matching_vote_not_answer_authorship(self):
        self.lobby.assign_special_role("Host_01", "Alice", Role.BRIDE)
        self.lobby.assign_special_role("Host_01", "Bob", Role.GROOM)

        self.lobby.start_game("Host_01", "Q1")
        self.lobby.submit_answer("Host_01", "host answer")
        self.lobby.submit_answer("Alice", "bride answer")
        self.lobby.submit_answer("Bob", "groom answer")
        self.lobby.submit_answer("Cara", "friend answer")
        self.lobby.start_voting("Host_01")

        options = {
            a["text"]: a["answer_id"]
            for a in self.lobby.to_client_payload("Host_01")["answers_for_voting"]
        }

        # BRIDE votes for GROOM answer. GROOM votes for BRIDE answer.
        self.lobby.submit_vote("Host_01", options["groom answer"])
        self.lobby.submit_vote("Alice", options["groom answer"])
        self.lobby.submit_vote("Bob", options["bride answer"])
        self.lobby.submit_vote("Cara", options["bride answer"])

        self.lobby.reveal_first_answer("Host_01")
        while self.lobby.current_round.reveal_target == TargetKind.FRIEND_BLOCK:
            self.lobby.reveal_votes("Host_01")
            self.lobby.reveal_next_after_votes("Host_01")

        self.lobby.reveal_votes("Host_01")
        self.lobby.reveal_next_after_votes("Host_01")
        self.lobby.reveal_votes("Host_01")
        self.lobby.reveal_next_after_votes("Host_01")

        self.assertEqual(self.lobby.phase, Phase.FINISH)
        boards = self.lobby.leaderboard_payload()
        self.assertEqual(dict(boards["voted_bride_most"]), {"Host_01": 1, "Alice": 1})
        self.assertEqual(dict(boards["voted_groom_most"]), {"Bob": 1, "Cara": 1})

    def test_host_and_friend_cannot_vote_own_answer(self):
        self.lobby.assign_special_role("Host_01", "Bob", Role.BRIDE)
        self.lobby.assign_special_role("Host_01", "Cara", Role.GROOM)
        self.lobby.start_game("Host_01", "Q1")
        self.lobby.submit_answer("Host_01", "Host answer")
        self.lobby.submit_answer("Alice", "A")
        self.lobby.submit_answer("Bob", "B")
        self.lobby.submit_answer("Cara", "C")
        self.lobby.start_voting("Host_01")

        host_options = self.lobby.to_client_payload("Host_01")["answers_for_voting"]
        host_own = next(a for a in host_options if a["is_own"]) ["answer_id"]

        alice_options = self.lobby.to_client_payload("Alice")["answers_for_voting"]
        alice_own = next(a for a in alice_options if a["is_own"]) ["answer_id"]

        with self.assertRaisesRegex(LobbyError, "cannot vote for your own answer"):
            self.lobby.submit_vote("Host_01", host_own)

        with self.assertRaisesRegex(LobbyError, "cannot vote for your own answer"):
            self.lobby.submit_vote("Alice", alice_own)

    def test_bride_and_groom_can_vote_own_answer(self):
        self.lobby.assign_special_role("Host_01", "Alice", Role.BRIDE)
        self.lobby.assign_special_role("Host_01", "Bob", Role.GROOM)
        self.lobby.start_game("Host_01", "Q1")

        self.lobby.submit_answer("Host_01", "Host answer")
        self.lobby.submit_answer("Alice", "Bride answer")
        self.lobby.submit_answer("Bob", "Groom answer")
        self.lobby.submit_answer("Cara", "Friend answer")
        self.lobby.start_voting("Host_01")

        bride_options = self.lobby.to_client_payload("Alice")["answers_for_voting"]
        bride_own = next(a for a in bride_options if a["is_own"]) ["answer_id"]
        groom_options = self.lobby.to_client_payload("Bob")["answers_for_voting"]
        groom_own = next(a for a in groom_options if a["is_own"]) ["answer_id"]
        self.lobby.submit_vote("Alice", bride_own)
        self.lobby.submit_vote("Bob", groom_own)

        self.assertEqual(self.lobby.submitted_votes_count(), 2)

    def test_to_client_payload_exposes_host_buttons_readiness_flags(self):
        self.lobby.assign_special_role("Host_01", "Alice", Role.BRIDE)
        self.lobby.assign_special_role("Host_01", "Bob", Role.GROOM)
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
        options = {
            a["text"]: a["answer_id"]
            for a in self.lobby.to_client_payload("Host_01")["answers_for_voting"]
        }
        self.lobby.submit_vote("Host_01", options["A"])
        self.lobby.submit_vote("Alice", options["B"])
        self.lobby.submit_vote("Bob", options["A"])

        host_payload = self.lobby.to_client_payload("Host_01")
        self.assertFalse(host_payload["host_can_reveal_first"])

        self.lobby.submit_vote("Cara", options["A"])
        host_payload = self.lobby.to_client_payload("Host_01")
        self.assertTrue(host_payload["host_can_reveal_first"])

    def test_duplicate_answers_are_grouped_and_votes_credit_all_authors(self):
        self.lobby.assign_special_role("Host_01", "Bob", Role.BRIDE)
        self.lobby.assign_special_role("Host_01", "Cara", Role.GROOM)
        self.lobby.start_game("Host_01", "Q1")
        self.lobby.submit_answer("Host_01", "same answer")
        self.lobby.submit_answer("Alice", "same answer")
        self.lobby.submit_answer("Bob", "unique one")
        self.lobby.submit_answer("Cara", "unique two")
        self.lobby.start_voting("Host_01")

        host_options = self.lobby.to_client_payload("Host_01")["answers_for_voting"]
        self.assertEqual(len(host_options), 3)
        merged = next(a for a in host_options if a["text"] == "same answer")
        self.assertTrue(merged["is_own"])
        self.assertTrue(merged["is_shared_own"])

        alice_options = self.lobby.to_client_payload("Alice")["answers_for_voting"]
        alice_merged = next(a for a in alice_options if a["text"] == "same answer")
        self.assertTrue(alice_merged["is_own"])
        self.assertTrue(alice_merged["is_shared_own"])

        merged_option_id = merged["answer_id"]
        unique_one_id = next(a for a in host_options if a["text"] == "unique one")["answer_id"]

        # HOST and FRIEND can vote for their own merged answer when it is shared.
        self.lobby.submit_vote("Host_01", merged_option_id)
        self.lobby.submit_vote("Alice", merged_option_id)
        self.lobby.submit_vote("Bob", merged_option_id)
        self.lobby.submit_vote("Cara", unique_one_id)

        self.lobby.reveal_first_answer("Host_01")
        while self.lobby.phase == Phase.REVEAL_ANSWER and self.lobby.current_round.reveal_target == TargetKind.FRIEND_BLOCK:
            self.lobby.reveal_votes("Host_01")
            self.lobby.reveal_next_after_votes("Host_01")

        self.lobby.reveal_votes("Host_01")
        self.lobby.reveal_next_after_votes("Host_01")
        self.lobby.reveal_votes("Host_01")
        self.lobby.reveal_next_after_votes("Host_01")

        self.assertEqual(self.lobby.phase, Phase.FINISH)
        boards = dict(self.lobby.leaderboard_payload()["most_votes"])
        self.assertEqual(boards["Host_01"], 3)
        self.assertEqual(boards["Alice"], 3)

    def test_reveal_collapses_duplicate_friend_answers_into_single_step(self):
        self.lobby.assign_special_role("Host_01", "Bob", Role.BRIDE)
        self.lobby.assign_special_role("Host_01", "Cara", Role.GROOM)
        self.lobby.start_game("Host_01", "Q1")
        self.lobby.submit_answer("Host_01", "same")
        self.lobby.submit_answer("Alice", "same")
        self.lobby.submit_answer("Bob", "unique")
        self.lobby.submit_answer("Cara", "other")
        self.lobby.start_voting("Host_01")

        options = {a["text"]: a["answer_id"] for a in self.lobby.to_client_payload("Host_01")["answers_for_voting"]}
        self.lobby.submit_vote("Host_01", options["same"])
        self.lobby.submit_vote("Alice", options["same"])
        self.lobby.submit_vote("Bob", options["same"])
        self.lobby.submit_vote("Cara", options["same"])

        self.lobby.reveal_first_answer("Host_01")
        first = self.lobby.get_current_reveal_answer()
        self.assertEqual(first["text"], "same")
        self.assertEqual(first["username"], "Host_01, Alice")

        self.lobby.reveal_votes("Host_01")
        payload = self.lobby.to_client_payload("Host_01")
        self.assertEqual(payload["current_reveal_answer"]["voted_by"], ["Alice", "Bob", "Cara", "Host_01"])

    def test_duplicate_with_bride_is_deferred_to_bride_turn(self):
        self.lobby.assign_special_role("Host_01", "Alice", Role.BRIDE)
        self.lobby.assign_special_role("Host_01", "Bob", Role.GROOM)

        self.lobby.start_game("Host_01", "Q1")
        self.lobby.submit_answer("Host_01", "same")
        self.lobby.submit_answer("Alice", "same")
        self.lobby.submit_answer("Bob", "groom only")
        self.lobby.submit_answer("Cara", "friend only")
        self.lobby.start_voting("Host_01")

        options = {a["text"]: a["answer_id"] for a in self.lobby.to_client_payload("Host_01")["answers_for_voting"]}
        self.lobby.submit_vote("Host_01", options["same"])
        self.lobby.submit_vote("Alice", options["same"])
        self.lobby.submit_vote("Bob", options["same"])
        self.lobby.submit_vote("Cara", options["same"])

        self.lobby.reveal_first_answer("Host_01")
        first = self.lobby.get_current_reveal_answer()
        self.assertEqual(first["text"], "friend only")

        self.lobby.reveal_votes("Host_01")
        self.lobby.reveal_next_after_votes("Host_01")
        bride_reveal = self.lobby.get_current_reveal_answer()
        self.assertEqual(bride_reveal["role"], "BRIDE")
        self.assertEqual(bride_reveal["username"], "Host_01, Alice")

    def test_bride_and_groom_same_answer_is_consolidated_on_bride_and_skips_groom(self):
        self.lobby.assign_special_role("Host_01", "Alice", Role.BRIDE)
        self.lobby.assign_special_role("Host_01", "Bob", Role.GROOM)

        self.lobby.start_game("Host_01", "Q1")
        self.lobby.submit_answer("Host_01", "host only")
        self.lobby.submit_answer("Alice", "same")
        self.lobby.submit_answer("Bob", "same")
        self.lobby.submit_answer("Cara", "friend only")
        self.lobby.start_voting("Host_01")

        options = {a["text"]: a["answer_id"] for a in self.lobby.to_client_payload("Host_01")["answers_for_voting"]}
        self.lobby.submit_vote("Host_01", options["same"])
        self.lobby.submit_vote("Alice", options["same"])
        self.lobby.submit_vote("Bob", options["same"])
        self.lobby.submit_vote("Cara", options["same"])

        self.lobby.reveal_first_answer("Host_01")
        while self.lobby.current_round.reveal_target == TargetKind.FRIEND_BLOCK:
            self.lobby.reveal_votes("Host_01")
            self.lobby.reveal_next_after_votes("Host_01")

        bride_reveal = self.lobby.get_current_reveal_answer()
        self.assertEqual(bride_reveal["role"], "BRIDE")
        self.assertEqual(bride_reveal["username"], "Alice, Bob")
        self.assertTrue(bride_reveal["includes_groom"])

        self.lobby.reveal_votes("Host_01")
        self.lobby.reveal_next_after_votes("Host_01")
        self.assertEqual(self.lobby.phase, Phase.FINISH)


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
