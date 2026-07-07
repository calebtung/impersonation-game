# Wedding Party Game

Real-time, phone-friendly party game for a wedding group.

One person creates a lobby as HOST, everyone joins with a 4-digit code, the host assigns BRIDE/GROOM tags, and each round runs:

1. Everyone submits an answer to the current question.
2. Everyone votes on the best/funniest answer (anonymized first).
3. Host reveals answers and voters in a staged reveal flow.
4. Scores/leaderboards are tracked across all questions.

At the end, a finish screen shows leaderboards and BRIDE/GROOM agreement stats.

Made with GitHub Copilot and lots of prompt engineering.

## Stack

- Backend: Flask + Flask-SocketIO
- Frontend: Vanilla JS + Socket.IO client
- Transport: WebSocket (Socket.IO)
- State: In-memory Python objects (no database)

## Project Structure

- `app.py`: Flask app + Socket.IO event handlers + lobby broadcasts
- `lobby.py`: Core game model/state machine (`Lobby`, `GameRegistry`, rules, transitions)
- `templates/index.html`: Single-page shell
- `static/app.js`: Client-side renderer and socket event emitters
- `static/styles.css`: UI styling

## Quick Start

## 1) Create and activate a virtual environment

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## 2) Install dependencies

```bash
pip install -r requirements.txt
```

## 3) Run the app

```bash
python app.py
```

Server starts on:

- `http://127.0.0.1:5000`
- `http://0.0.0.0:5000` (bound to all interfaces)

## 4) Play from phones on the same Wi-Fi

1. Start the server on your laptop.
2. Find your laptop's LAN IP (example: `192.168.1.42`).
3. Ask everyone to open `http://<LAN_IP>:5000` in mobile browser.
4. Host taps **Create Lobby** and shares the 4-digit lobby code.
5. Everyone else taps **Join Lobby**.

If people cannot connect:

- Confirm all devices are on the same network.
- Allow port `5000` in firewall settings.
- Avoid guest Wi-Fi networks that isolate clients.

## Roles and Rules

Roles:

- HOST: creates/controls lobby and progression
- BRIDE: special role assigned by host
- GROOM: special role assigned by host
- FRIEND: default role for everyone else

Important rules implemented:

- Username must match: letters/numbers/underscore, 2-20 chars.
- Lobby code is random 4 digits.
- Only host can assign BRIDE/GROOM/FRIEND roles.
- BRIDE and GROOM are unique; assigning a new one demotes the previous holder to FRIEND.
- Host can start voting only after all answers are submitted.
- Host can reveal answers only after all votes are submitted.
- HOST and FRIEND cannot vote for their own answer.
- BRIDE and GROOM can vote for their own answer.
- If host leaves/disconnects, lobby closes for everyone.

## Game Flow (Implemented)

This code supports the full flow requested through role-specific UI states.

High-level phase progression:

1. `LOBBY`
2. `QUESTION`
3. `VOTING`
4. `REVEAL_ANSWER`
5. `REVEAL_VOTES`
6. Repeat reveal substeps until round ends
7. Next question -> back to `QUESTION`, or final -> `FINISH`

Role-specific UI state names are generated from phase + role (examples):

- `HOSTGAMEQUESTION`, `BRIDEGAMEQUESTION`, `FRIENDGAMEQUESTION`
- `HOSTGAMEVOTING`, `GROOMGAMEVOTING`, etc.
- `HOSTGAMEREVEAL`, `HOSTGAMEREVEALBRIDE`, `HOSTGAMEREVEALGROOM`
- `HOSTGAMEREVEALVOTE`, `HOSTGAMEREVEALVOTEBRIDE`, `HOSTGAMEREVEALVOTEGROOM`
- `HOSTFINISH`, `BRIDEFINISH`, `GROOMFINISH`, `FRIENDFINISH`

Reveal ordering is enforced as:

1. HOST answer
2. FRIEND answers (alphabetical by username inside role grouping)
3. BRIDE answer
4. GROOM answer

## Leaderboards and Stats

At finish, app computes and displays:

- **Who Got the Most Votes**
- **Who Voted for BRIDE Most Often**
- **Who Voted for GROOM Most Often**
- **BRIDE/GROOM Agreement**: number of questions where bride and groom voted the same answer

## Socket Events (Reference)

Client -> server:

- `create_lobby`
- `join_lobby`
- `leave_lobby`
- `close_lobby`
- `assign_role`
- `set_questions` (supported by backend)
- `start_game`
- `submit_answer`
- `start_voting`
- `submit_vote`
- `reveal_first_answer`
- `reveal_votes`
- `next_reveal_step`
- `return_to_lobby`

Server -> client:

- `connected`
- `state_update`
- `game_error`
- `left_lobby`
- `lobby_closed`

## Data Model Notes

- `questions_list`: ordered list of host-entered questions
- `answers_dict[question_index]`: ordered saved answers with:
  - `answer_id`
  - `username`
  - `role`
  - `text`
  - `voted_by` (filled during reveal-votes/finalization)
- Per-round transient state tracks:
  - submitted answers
  - submitted votes
  - current reveal target and index

## Operational Notes

Current implementation is great for a single party session, but keep in mind:

- In-memory state only: restarting server clears all lobbies/game history.
- Single-process assumptions: horizontal scaling would need shared state.
- No auth/accounts: usernames are lobby-scoped only.
- `SECRET_KEY` in `app.py` should be changed for non-local use.
- CORS is open (`cors_allowed_origins="*"`) for convenience.

## Hosting Tips for an Event

- Use a stable laptop plugged into power.
- Keep browser tab/server process open the whole party.
- Test with 2-3 phones before guests arrive.
- Prepare questions in advance and paste into host textbox/
