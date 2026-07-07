const socket = io();

const state = {
  localScreen: "LAUNCHPAGE",
  username: "",
  lobbyCode: "",
  latest: null,
  drafts: {
    createUsername: "",
    joinUsername: "",
    joinCode: "",
    hostQuestions: "",
    answerByQuestion: {},
    roleSelectionByUser: {},
  },
};

const appEl = document.getElementById("app");
const statusLine = document.getElementById("status-line");
const errorBox = document.getElementById("error-box");

function clearError() {
  errorBox.classList.add("hidden");
  errorBox.textContent = "";
}

function showError(message) {
  errorBox.classList.remove("hidden");
  errorBox.textContent = message;
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function roleTag(role, isHost) {
  if (isHost) return '<span class="tag tag-host">HOST</span>';
  if (role === "BRIDE") return '<span class="tag tag-bride">BRIDE</span>';
  if (role === "GROOM") return '<span class="tag tag-groom">GROOM</span>';
  return '<span class="tag tag-friend">FRIEND</span>';
}

function selectedAttr(value, expected) {
  return value === expected ? "selected" : "";
}

function renderLaunch() {
  appEl.innerHTML = `
    <section class="card">
      <div class="button-row cols-2">
        <button id="go-create">Create Lobby</button>
        <button id="go-join">Join Lobby</button>
      </div>
    </section>
  `;
  document.getElementById("go-create").onclick = () => {
    clearError();
    state.localScreen = "CREATELOBBY";
    render();
  };
  document.getElementById("go-join").onclick = () => {
    clearError();
    state.localScreen = "JOINLOBBY";
    render();
  };
}

function renderCreateLobby() {
  const draftUsername = state.drafts.createUsername || state.username;
  appEl.innerHTML = `
    <section class="card">
      <h2>Create Lobby</h2>
      <label>Username</label>
      <input id="create-username" maxlength="20" placeholder="Host username" value="${esc(draftUsername)}" />
      <div style="height: 8px"></div>
      <button id="create-submit">Enter Lobby</button>
    </section>
    <section class="card">
      <button id="create-back">Back</button>
    </section>
  `;
  document.getElementById("create-back").onclick = () => {
    clearError();
    state.localScreen = "LAUNCHPAGE";
    render();
  };
  document.getElementById("create-username").oninput = (e) => {
    state.drafts.createUsername = e.target.value;
  };
  document.getElementById("create-submit").onclick = () => {
    clearError();
    const username = document.getElementById("create-username").value.trim();
    state.username = username;
    state.drafts.createUsername = username;
    socket.emit("create_lobby", { username });
  };
}

function renderJoinLobby() {
  const draftCode = state.drafts.joinCode || state.lobbyCode;
  const draftUsername = state.drafts.joinUsername || state.username;
  appEl.innerHTML = `
    <section class="card">
      <h2>Join Lobby</h2>
      <label>Lobby Code</label>
      <input id="join-code" maxlength="4" placeholder="4-digit code" value="${esc(draftCode)}" />
      <label style="margin-top: 8px">Username</label>
      <input id="join-username" maxlength="20" placeholder="Your username" value="${esc(draftUsername)}" />
      <div style="height: 8px"></div>
      <button id="join-submit">Enter Lobby</button>
    </section>
    <section class="card">
      <button id="join-back">Back</button>
    </section>
  `;
  document.getElementById("join-back").onclick = () => {
    clearError();
    state.localScreen = "LAUNCHPAGE";
    render();
  };
  document.getElementById("join-code").oninput = (e) => {
    state.drafts.joinCode = e.target.value;
  };
  document.getElementById("join-username").oninput = (e) => {
    state.drafts.joinUsername = e.target.value;
  };
  document.getElementById("join-submit").onclick = () => {
    clearError();
    const code = document.getElementById("join-code").value.trim();
    const username = document.getElementById("join-username").value.trim();
    state.username = username;
    state.lobbyCode = code;
    state.drafts.joinCode = code;
    state.drafts.joinUsername = username;
    socket.emit("join_lobby", { code, username });
  };
}

function renderPlayers(players, isHost) {
  return `
    <ul class="list">
      ${players
        .map((p) => {
          const selectedRole = state.drafts.roleSelectionByUser[p.username] || p.role;
          const options = isHost
            ? `
              <select class="role-select" data-user="${esc(p.username)}">
                <option value="FRIEND" ${selectedAttr(selectedRole, "FRIEND")}>FRIEND</option>
                <option value="BRIDE" ${selectedAttr(selectedRole, "BRIDE")}>BRIDE</option>
                <option value="GROOM" ${selectedAttr(selectedRole, "GROOM")}>GROOM</option>
              </select>
            `
            : "";
          const controls =
            isHost && !p.is_host
              ? `<div style="margin-top: 6px">${options}</div><button class="assign-role" data-user="${esc(
                  p.username
                )}">Assign</button>`
              : "";
          return `
            <li>
              <strong>${esc(p.username)}</strong>${roleTag(p.role, p.is_host)}
              ${controls}
            </li>
          `;
        })
        .join("")}
    </ul>
  `;
}

function renderLobby(data) {
  const isHost = data.role === "HOST";
  const hostQuestionsDraft = state.drafts.hostQuestions || "";
  appEl.innerHTML = `
    <section class="card">
      <h2>${isHost ? "Host Lobby" : "Lobby"}</h2>
      <p class="small">Lobby Code: <strong>${esc(data.lobby_code)}</strong></p>
      <p class="small">Players: ${data.player_count}</p>
      ${renderPlayers(data.players, isHost)}
    </section>
    ${
      isHost
        ? `
      <section class="card">
        <label>Questions (one per line)</label>
        <textarea id="questions-box" placeholder="Type questions here">${esc(hostQuestionsDraft)}</textarea>
        <div style="height:8px"></div>
        <button id="start-game">Start Game</button>
        <div style="height:8px"></div>
        <button id="close-lobby">Close Lobby</button>
      </section>
    `
        : `
      <section class="card">
        <button id="leave-lobby">Leave Lobby</button>
      </section>
    `
    }
  `;

  document.querySelectorAll(".assign-role").forEach((btn) => {
    btn.onclick = () => {
      const parent = btn.parentElement;
      const select = parent.querySelector(".role-select");
      const targetUsername = btn.dataset.user;
      const role = state.drafts.roleSelectionByUser[targetUsername] || select.value;
      state.drafts.roleSelectionByUser[targetUsername] = role;
      socket.emit("assign_role", { target_username: targetUsername, role });
    };
  });

  document.querySelectorAll(".role-select").forEach((select) => {
    select.oninput = (e) => {
      const targetUsername = e.target.dataset.user;
      if (!targetUsername) {
        return;
      }
      state.drafts.roleSelectionByUser[targetUsername] = e.target.value;
    };
  });

  const questionsBox = document.getElementById("questions-box");
  if (questionsBox) {
    questionsBox.oninput = (e) => {
      state.drafts.hostQuestions = e.target.value;
    };
  }

  const startGame = document.getElementById("start-game");
  if (startGame) {
    startGame.onclick = () => {
      const questionsText = (document.getElementById("questions-box")?.value || "").trim();
      state.drafts.hostQuestions = questionsText;
      socket.emit("start_game", { questions_text: questionsText });
    };
  }

  const closeLobby = document.getElementById("close-lobby");
  if (closeLobby) {
    closeLobby.onclick = () => socket.emit("close_lobby");
  }

  const leaveLobby = document.getElementById("leave-lobby");
  if (leaveLobby) {
    leaveLobby.onclick = () => {
      socket.emit("leave_lobby");
      state.latest = null;
      state.localScreen = "LAUNCHPAGE";
      render();
    };
  }
}

function renderQuestion(data) {
  const isHost = data.role === "HOST";
  const questionKey = String(data.question_index);
  const answerDraft = state.drafts.answerByQuestion[questionKey] || "";
  appEl.innerHTML = `
    <section class="card">
      <h2>${esc(data.ui_state)}</h2>
      <p><strong>Question ${data.question_index + 1}/${data.question_total}</strong></p>
      <p>${esc(data.current_question || "")}</p>
      <label>Your Answer</label>
      <input id="answer-box" placeholder="Type short answer" value="${esc(answerDraft)}" ${data.player_has_answered ? "disabled" : ""} />
      <div style="height:8px"></div>
      <button id="answer-submit" ${data.player_has_answered ? "disabled" : ""}>Submit</button>
      <p class="small">Submitted: ${data.submitted_answers_count}/${data.player_count}</p>
      ${
        isHost
          ? `<button id="start-voting" ${data.host_can_start_voting ? "" : "disabled"}>Start Voting</button>`
          : ""
      }
    </section>
  `;

  const submitBtn = document.getElementById("answer-submit");
  const answerInput = document.getElementById("answer-box");
  if (answerInput && !data.player_has_answered) {
    answerInput.oninput = (e) => {
      state.drafts.answerByQuestion[questionKey] = e.target.value;
    };
  }
  if (submitBtn) {
    submitBtn.onclick = () => {
      const answer = document.getElementById("answer-box").value;
      state.drafts.answerByQuestion[questionKey] = answer;
      socket.emit("submit_answer", { answer });
    };
  }

  const startVoting = document.getElementById("start-voting");
  if (startVoting) {
    startVoting.onclick = () => socket.emit("start_voting");
  }
}

function renderVoting(data) {
  const isHost = data.role === "HOST";
  const voteButtons = data.answers_for_voting
    .map((a) => {
      const disableOwn = (data.role === "HOST" || data.role === "FRIEND") && a.is_own;
      const disabled = data.player_has_voted || disableOwn;
      return `
        <button class="answer-btn ${a.is_own ? "answer-own" : ""}" data-answer-id="${esc(a.answer_id)}" ${
        disabled ? "disabled" : ""
      }>
          ${a.is_own ? "(Your answer) " : ""}${esc(a.text)}
        </button>
      `;
    })
    .join("");

  appEl.innerHTML = `
    <section class="card">
      <h2>${esc(data.ui_state)}</h2>
      <p><strong>Question ${data.question_index + 1}/${data.question_total}</strong></p>
      <p>${esc(data.current_question || "")}</p>
      <div>${voteButtons}</div>
      <p class="small">Votes: ${data.submitted_votes_count}/${data.player_count}</p>
      ${
        isHost
          ? `<button id="reveal-first" ${data.host_can_reveal_first ? "" : "disabled"}>Reveal First Answer</button>`
          : ""
      }
    </section>
  `;

  document.querySelectorAll(".answer-btn").forEach((btn) => {
    btn.onclick = () => {
      const answerId = btn.dataset.answerId;
      socket.emit("submit_vote", { answer_id: answerId });
    };
  });

  const revealFirst = document.getElementById("reveal-first");
  if (revealFirst) {
    revealFirst.onclick = () => socket.emit("reveal_first_answer");
  }
}

function actionLabelForRevealVotes(data) {
  if (!data.current_reveal_answer) {
    return "Next";
  }
  const role = data.current_reveal_answer.role;
  if (role === "HOST" || role === "FRIEND") {
    const friendAnswers = data.answers_for_voting.filter((a) => {
      const r = a.author_role;
      return r === "HOST" || r === "FRIEND";
    });
    const currentIndex = friendAnswers.findIndex((a) => a.answer_id === data.current_reveal_answer.answer_id);
    if (currentIndex >= 0 && currentIndex + 1 < friendAnswers.length) {
      return "Reveal Next Answer";
    }
    return "Reveal Bride Answer";
  }
  if (role === "BRIDE") {
    return "Reveal Groom Answer";
  }
  if (data.question_index + 1 < data.question_total) {
    return "Next Question";
  }
  return "Finish Game";
}

function renderReveal(data) {
  const isHost = data.role === "HOST";
  const current = data.current_reveal_answer;
  const voters = data.answers_for_voting.find((a) => a.answer_id === current?.answer_id)?.voted_by || [];
  const inVoteSubstep = data.phase === "REVEAL_VOTES";

  appEl.innerHTML = `
    <section class="card">
      <h2>${esc(data.ui_state)}</h2>
      <p><strong>Question ${data.question_index + 1}/${data.question_total}</strong></p>
      <p>${esc(data.current_question || "")}</p>
      ${
        current
          ? `
        <p><strong>${esc(current.username)}</strong> (${esc(current.role)}): ${esc(current.text)}</p>
      `
          : `<p class="small">No answer available for this reveal slot.</p>`
      }
      ${
        inVoteSubstep
          ? `<p class="small">Votes: ${voters.length ? esc(voters.join(", ")) : "No votes"}</p>`
          : ""
      }
      ${
        isHost
          ? inVoteSubstep
            ? `<button id="host-next-reveal">${esc(actionLabelForRevealVotes(data))}</button>`
            : `<button id="host-reveal-votes">Reveal Votes</button>`
          : ""
      }
    </section>
  `;

  const revealVotesBtn = document.getElementById("host-reveal-votes");
  if (revealVotesBtn) {
    revealVotesBtn.onclick = () => socket.emit("reveal_votes");
  }

  const nextRevealBtn = document.getElementById("host-next-reveal");
  if (nextRevealBtn) {
    nextRevealBtn.onclick = () => socket.emit("next_reveal_step");
  }
}

function leaderboardList(title, items) {
  const rows = items.length
    ? items.map((x) => `<li><strong>${esc(x[0])}</strong>: ${esc(x[1])}</li>`).join("")
    : '<li class="small">No data</li>';
  return `
    <section class="card">
      <h3>${esc(title)}</h3>
      <ul class="list">${rows}</ul>
    </section>
  `;
}

function renderFinish(data) {
  const boards = data.leaderboards || {
    most_votes: [],
    voted_bride_most: [],
    voted_groom_most: [],
    bride_groom_agreement: { agreed: 0, total_questions: 0 },
  };

  appEl.innerHTML = `
    ${leaderboardList("Who Got the Most Votes", boards.most_votes)}
    ${leaderboardList("Who Voted for BRIDE Most Often", boards.voted_bride_most)}
    ${leaderboardList("Who Voted for GROOM Most Often", boards.voted_groom_most)}
    <section class="card stat-grid">
      <h3>Bride/Groom Agreement</h3>
      <p>${esc(boards.bride_groom_agreement.agreed)} / ${esc(boards.bride_groom_agreement.total_questions)}</p>
      ${data.role === "HOST" ? '<button id="return-lobby">Return to Lobby</button>' : ""}
    </section>
  `;

  const returnBtn = document.getElementById("return-lobby");
  if (returnBtn) {
    returnBtn.onclick = () => socket.emit("return_to_lobby");
  }
}

function renderFromServerState(data) {
  const ui = data.ui_state;
  if (ui === "HOSTLOBBY" || ui === "EVERYONELOBBY") {
    renderLobby(data);
    return;
  }
  if (ui.endsWith("GAMEQUESTION")) {
    renderQuestion(data);
    return;
  }
  if (ui.endsWith("GAMEVOTING")) {
    renderVoting(data);
    return;
  }
  if (ui.includes("GAMEREVEAL")) {
    renderReveal(data);
    return;
  }
  if (ui.endsWith("FINISH")) {
    renderFinish(data);
    return;
  }

  appEl.innerHTML = `<section class="card"><p>Unknown state: ${esc(ui)}</p></section>`;
}

function render() {
  if (state.latest) {
    renderFromServerState(state.latest);
    return;
  }
  if (state.localScreen === "CREATELOBBY") {
    renderCreateLobby();
    return;
  }
  if (state.localScreen === "JOINLOBBY") {
    renderJoinLobby();
    return;
  }
  renderLaunch();
}

socket.on("connect", () => {
  statusLine.textContent = "Connected";
});

socket.on("disconnect", () => {
  statusLine.textContent = "Disconnected";
});

socket.on("connected", () => {
  clearError();
  render();
});

socket.on("game_error", (payload) => {
  showError(payload.message || "Unknown error");
});

socket.on("state_update", (payload) => {
  clearError();
  state.latest = payload;
  state.lobbyCode = payload.lobby_code;
  state.username = payload.username;
  if (!state.drafts.createUsername) {
    state.drafts.createUsername = payload.username;
  }
  if (!state.drafts.joinUsername) {
    state.drafts.joinUsername = payload.username;
  }
  render();
});

socket.on("left_lobby", () => {
  state.latest = null;
  state.localScreen = "LAUNCHPAGE";
  state.drafts.hostQuestions = "";
  state.drafts.answerByQuestion = {};
  render();
});

socket.on("lobby_closed", (payload) => {
  showError(payload.reason || "Lobby was closed");
  state.latest = null;
  state.localScreen = "LAUNCHPAGE";
  state.drafts.hostQuestions = "";
  state.drafts.answerByQuestion = {};
  render();
});

render();
