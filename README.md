# Wedding Party Browser Game

A real-time phone browser game for weddings and in-room parties.

One player is the HOST, one is BRIDE, one is GROOM, everyone else is FRIEND.
Players answer prompts, vote anonymously, then reveal who wrote what and who voted for what.

This README is written for two goals:

1. Run and test locally.
2. Host on a public VPS so everyone can join from their phones.

## What The Game Supports

- 4-digit lobby code creation and join flow.
- Live lobby list with role tags.
- HOST-controlled BRIDE/GROOM assignment (unique per role, replacement-safe).
- Question list entry (newline-separated).
- Per-question answer submit phase with live completion counter.
- Anonymous voting with role-aware self-vote rules.
- Multi-step reveal flow:
  - friend/host block answers
  - bride answer
  - groom answer
  - votes shown per revealed answer
- End-of-game leaderboards and BRIDE/GROOM agreement stat.
- Return to lobby for a fresh game.

## State Machine Mapping

The implementation uses a compact backend phase engine plus per-role UI state names.

Backend phases:

- LOBBY
- QUESTION
- VOTING
- REVEAL_ANSWER
- REVEAL_VOTES
- FINISH

Per-player UI states emitted by server payload:

- LOBBY
  - HOSTLOBBY
  - EVERYONELOBBY
- QUESTION
  - HOSTGAMEQUESTION
  - BRIDEGAMEQUESTION
  - GROOMGAMEQUESTION
  - FRIENDGAMEQUESTION
- VOTING
  - HOSTGAMEVOTING
  - BRIDEGAMEVOTING
  - GROOMGAMEVOTING
  - FRIENDGAMEVOTING
- REVEAL_ANSWER
  - HOSTGAMEREVEAL / BRIDEGAMEREVEAL / GROOMGAMEREVEAL / FRIENDGAMEREVEAL
  - HOSTGAMEREVEALBRIDE / BRIDEGAMEREVEALBRIDE / GROOMGAMEREVEALBRIDE / FRIENDGAMEREVEALBRIDE
  - HOSTGAMEREVEALGROOM / BRIDEGAMEREVEALGROOM / GROOMGAMEREVEALGROOM / FRIENDGAMEREVEALGROOM
- REVEAL_VOTES
  - HOSTGAMEREVEALVOTE / BRIDEGAMEREVEALVOTE / GROOMGAMEREVEALVOTE / FRIENDGAMEREVEALVOTE
  - HOSTGAMEREVEALVOTEBRIDE / BRIDEGAMEREVEALVOTEBRIDE / GROOMGAMEREVEALVOTEBRIDE / FRIENDGAMEREVEALVOTEBRIDE
  - HOSTGAMEREVEALVOTEGROOM / BRIDEGAMEREVEALVOTEGROOM / GROOMGAMEREVEALVOTEGROOM / FRIENDGAMEREVEALVOTEGROOM
- FINISH
  - HOSTFINISH
  - BRIDEFINISH
  - GROOMFINISH
  - FRIENDFINISH

Reveal order implemented:

1. HOST + FRIEND block (HOST first, then FRIEND answers)
2. BRIDE answer
3. GROOM answer

## Rules Implemented In Code

- Username validation: 2-20 chars, letters/numbers/underscore only.
- HOST role cannot be reassigned.
- BRIDE and GROOM are unique roles; assigning a new one demotes previous holder to FRIEND.
- HOST can only start voting after all players submit answers.
- HOST can only reveal first answer after all players submit votes.
- Self-vote rules:
  - HOST and FRIEND cannot vote a purely self-authored option.
  - BRIDE and GROOM can vote their own option.
- Duplicate identical answers are grouped into one voting option.
- If HOST disconnects or leaves, lobby is closed for everyone.

## Project Layout

- app.py
  - Flask app and Socket.IO event handlers.
  - SID/lobby binding, broadcasts, audit logging.
- lobby.py
  - Core game model, transitions, reveal routing, leaderboard scoring.
- templates/index.html
  - Single-page shell.
- static/app.js
  - Client renderer and socket interactions.
- static/styles.css
  - Mobile-first UI styling.
- tests/test_lobby.py
  - Unit tests for transitions and scoring.
- tests/test_ui_integration.py
  - Browser integration tests with Playwright.

## Local Development

### 1) Create virtual environment

python3 -m venv .venv
source .venv/bin/activate

### 2) Install dependencies

pip install -r requirements-dev.txt

### 3) Run app

.venv/bin/python app.py

Open in browser:

http://127.0.0.1:5000

### 4) Run tests

.venv/bin/python -m unittest discover -s tests -p "test_*.py"

Notes:

- UI integration tests require Playwright and Chromium.
- If Chromium is missing, run: .venv/bin/python -m playwright install chromium

## How To Play (Party Instructions)

### Host setup flow

1. Open the site and tap Create Lobby.
2. Enter HOST username and enter the lobby.
3. Tell guests the 4-digit lobby code.
4. Assign one BRIDE and one GROOM in lobby controls.
5. Paste questions (one question per line).
6. Tap Start Game.

### Round flow

1. Everyone answers the prompt.
2. HOST starts voting after all answers are in.
3. Everyone votes anonymously.
4. HOST reveals answers and then votes for each answer.
5. HOST advances to next question or finishes game at end.

### End flow

1. Everyone sees leaderboards and agreement stats.
2. HOST taps Return to Lobby for a fresh game.

## Production Hosting On A VPS (Open Internet)

Target stack:

- Ubuntu VPS
- systemd service for the Python app
- Nginx reverse proxy with WebSocket headers
- HTTPS via Let’s Encrypt

Recommended VPS size for about 25 players:

- 2 vCPU
- 2 GB RAM

### 1) DNS and server prep

Create an A record, for example:

party.example.com -> YOUR_VPS_IP

SSH in and install packages:

sudo apt-get update
sudo apt-get install -y python3 python3-venv nginx certbot python3-certbot-nginx

### 2) Deploy project

sudo mkdir -p /opt/impersonation-game
sudo chown "$USER":"$USER" /opt/impersonation-game

Copy project files into /opt/impersonation-game, then:

cd /opt/impersonation-game
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

### 3) Create environment file

Create /opt/impersonation-game/.env:

SECRET_KEY=replace-with-a-long-random-secret
IMPERSONATION_AUDIT_LOG_PATH=/opt/impersonation-game/logs/answer_vote_audit.json

Important current behavior in app.py:

- SECRET_KEY is still hardcoded in code.
- debug=True is enabled in code.

Before public launch, update app.py to read SECRET_KEY and debug mode from environment.

### 4) Create systemd service

Create /etc/systemd/system/impersonation-game.service

[Unit]
Description=Impersonation Game (Flask-SocketIO)
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/impersonation-game
EnvironmentFile=/opt/impersonation-game/.env
ExecStart=/opt/impersonation-game/.venv/bin/python /opt/impersonation-game/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target

Then enable and start:

sudo mkdir -p /opt/impersonation-game/logs
sudo chown -R www-data:www-data /opt/impersonation-game
sudo systemctl daemon-reload
sudo systemctl enable impersonation-game
sudo systemctl start impersonation-game
sudo systemctl status impersonation-game

### 5) Nginx config (HTTP + WebSocket proxy)

Create /etc/nginx/sites-available/impersonation-game:

server {
    listen 80;
    server_name party.example.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_read_timeout 3600;
        proxy_send_timeout 3600;
    }
}

Enable and reload:

sudo ln -s /etc/nginx/sites-available/impersonation-game /etc/nginx/sites-enabled/impersonation-game
sudo nginx -t
sudo systemctl reload nginx

### 6) Enable HTTPS

sudo certbot --nginx -d party.example.com

### 7) Firewall

sudo ufw allow OpenSSH
sudo ufw allow "Nginx Full"
sudo ufw enable
sudo ufw status

### 8) Party-day smoke test

1. Open https://party.example.com on at least 3 phones.
2. Run one full round: answer, vote, reveal, next question.
3. Watch logs live:

sudo journalctl -u impersonation-game -f

## Socket Events

Client to server:

- create_lobby
- join_lobby
- leave_lobby
- close_lobby
- assign_role
- set_questions
- start_game
- submit_answer
- start_voting
- submit_vote
- reveal_first_answer
- reveal_votes
- next_reveal_step
- return_to_lobby

Server to client:

- connected
- state_update
- game_error
- left_lobby
- lobby_closed

## Operational Notes

- Runtime state is in memory only. Restarting service resets active lobbies/games.
- This is designed for a single server process, not horizontal scaling.
- Client and server currently normalize usernames/questions/answers to lowercase.
- CORS is open in current app configuration.

## Suggested Pre-Event Checklist

1. Run all tests.
2. Verify BRIDE/GROOM assignment and reassignment behavior.
3. Verify reveal sequence with at least one dry run.
4. Prepare your question list in advance and paste into host panel.
5. Keep a backup device signed in as HOST.
