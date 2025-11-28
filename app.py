from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any

from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from threading import Lock
import os
import random

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")


class UserState(Enum):
  ENTERING = "entering"
  READY = "ready"
  PLAYER = "player"
  READER = "reader"


@dataclass
class UserInfo:
  """In-memory info stored per user while the server runs."""

  state: UserState = UserState.ENTERING
  text: str = ""


class GameState(Enum):
  WAITING_FOR_PLAYERS = "waiting_for_players"
  GAME_WAITING_FOR_DEFINITIONS = "game_waiting_for_definitions"
  GAME_WAITING_FOR_DECISION_IRL = "game_waiting_for_decision_irl"


@dataclass
class AppState:
  """Global application state held in-memory while the process runs."""

  state: GameState = GameState.WAITING_FOR_PLAYERS
  info: Dict[str, Any] | None = None
  # becomes True the first time all users are ready (and minimum player requirement met)
  started: bool = False
  word: str | None = None


# In-memory storage for usernames while the server is running
usersdb: Dict[str, UserInfo] = {}
USERS_LOCK = Lock()

# Global application state
app_state = AppState()
STATE_LOCK = Lock()

# Convenience: add two fake users for quick local testing when the
# environment variable `BINDOLO_FAKE_USERS=1` is set. This is temporary
# and safe for development — it won't run unless you set the env var.
if os.getenv("BINDOLO_FAKE_USERS") == "1":
  with USERS_LOCK:
    usersdb.setdefault("alice", UserInfo())
    usersdb.setdefault("bob", UserInfo())


@app.route("/", methods=["GET"])
def index():
  # pass the current mapping of stored usernames to the template
  with USERS_LOCK:
    current = {k: {"state": v.state.value, "text": v.text} for k, v in usersdb.items()}
  with STATE_LOCK:
    current_state = app_state.state.value
  return render_template("index.html", usersdb=current, state=current_state)


@app.route("/landing", methods=["POST"])
def landing():
  username = request.form.get("username", "").strip()
  if not username:
    return redirect(url_for("index"))

  # Only allow new users while the app is waiting for players
  with STATE_LOCK:
    current_state = app_state.state
    started = app_state.started

  if current_state is not GameState.WAITING_FOR_PLAYERS or started:
    # registration closed — show informative landing with rejection
    if started:
      reason = "Registration is closed: game already started for this session."
    else:
      reason = f"Registration is closed (state={current_state.value})."
    return render_template(
      "landing.html", username=username, accepted=False, reason=reason
    )

  # register user in-memory (no counter)
  with USERS_LOCK:
    info = usersdb.get(username)
    if info is None:
      info = UserInfo()
      usersdb[username] = info

    # persist username in session so subsequent pages know which user this is
    session["username"] = username

  return render_template(
    "landing.html", username=username, accepted=True, user_state=info.state.value
  )


@app.route("/user/state", methods=["POST"])
def set_user_state():
  # Accept JSON or form data with `username` and `state`
  data = request.get_json(silent=True) or request.form
  username = data.get("username") if hasattr(data, "get") else None
  state_val = data.get("state") if hasattr(data, "get") else None
  if not username or not state_val:
    return jsonify({"error": "username and state are required"}), 400

  with USERS_LOCK:
    user = usersdb.get(username)
    if user is None:
      return jsonify({"error": "user not found"}), 404
    try:
      new_state = UserState(state_val)
    except ValueError:
      # allow passing enum name as alternative
      try:
        new_state = UserState[state_val.upper()]
      except Exception:
        return jsonify({"error": "invalid state"}), 400
    user.state = new_state

  # After updating the user's state, check whether all users are READY
  with USERS_LOCK:
    total = len(usersdb)
    necessary_players = total >= 3
    all_ready = total > 0 and all(v.state is UserState.READY for v in usersdb.values())

  # If all are ready and we've reached the minimum players, mark the game started
  if necessary_players and all_ready:
    with STATE_LOCK:
      if app_state.state is GameState.WAITING_FOR_PLAYERS:
        app_state.state = GameState.GAME_WAITING_FOR_DEFINITIONS
      if not app_state.started:
        app_state.started = True
        # Assign roles: pick one random user as READER, others become PLAYER
        with USERS_LOCK:
          usernames = list(usersdb.keys())
          if usernames:
            reader = random.choice(usernames)
            for uname, u in usersdb.items():
              if uname == reader:
                u.state = UserState.READER
              else:
                u.state = UserState.PLAYER

  # return the new state and whether the game has started
  with STATE_LOCK:
    started_flag = app_state.started

  return jsonify(
    {"username": username, "state": user.state.value, "started": started_flag}
  )


@app.route("/usersdb", methods=["GET"])
def get_users():
  # return simple status booleans used by the landing page polling JS
  # - `necessary_players`: true when we have at least the minimum number of players
  # - `all_ready`: true when there is at least one user and every user is in the READY state
  with USERS_LOCK:
    total = len(usersdb)
    necessary_players = total >= 3
    # the all ready might need to be tweaked a bit: I do not thing it is robust to rely only on ENTERING here
    all_ready = total > 0 and all(
      v.state is not UserState.ENTERING for v in usersdb.values()
    )
    return jsonify({"necessary_players": necessary_players, "all_ready": all_ready})


@app.route("/players", methods=["GET"])
def get_players():
  # return a simple mapping of username -> state (no text)
  with USERS_LOCK:
    return jsonify({k: v.state.value for k, v in usersdb.items()})


@app.route("/state", methods=["GET"])
def get_state():
  with STATE_LOCK:
    return jsonify(
      {
        "state": app_state.state.value,
        "info": app_state.info or {},
        "started": app_state.started,
      }
    )


@app.route("/clear", methods=["POST"])
def clear_users():
  # clear the in-memory storage
  with USERS_LOCK:
    usersdb.clear()
  return redirect(url_for("index"))


@app.route("/admin", methods=["GET"])
def admin():
  return render_template("admin.html")


@app.route("/play", methods=["GET"])
def play():
  # Simple play page: determine username from session and pass user's state
  username = session.get("username")
  user_state = None
  if username:
    with USERS_LOCK:
      user = usersdb.get(username)
      if user is not None:
        user_state = user.state.value

  return render_template("play.html", username=username, user_state=user_state)


@app.route("/reading", methods=["GET"])
def reading():
  # Show the reading page. Players see the reader's word; the reader sees a carousel
  # of player-submitted texts.
  username = session.get("username")
  user_state = None
  with USERS_LOCK:
    if username:
      user = usersdb.get(username)
      if user is not None:
        user_state = user.state.value

    # collect player texts (exclude empty)
    player_texts = [
      {"username": uname, "text": u.text}
      for uname, u in usersdb.items()
      if (u.text is not None and u.text != "")
    ]
  with STATE_LOCK:
    word = app_state.word

  return render_template(
    "reading.html",
    username=username,
    user_state=user_state,
    game_word=word,
    player_texts=player_texts,
  )


@app.route("/play/submit", methods=["POST"])
def play_submit():
  """Single submit endpoint for both PLAYER and READER roles.

  Behavior depends on the user's current `UserState` stored in `usersdb`:
  - PLAYER: expects JSON/form `text` and stores it on `user.text`.
  - READER: expects `word` and optional `text`. Stores `app_state.word` and
    `user.text`.

  After saving, the handler checks whether all participants have provided
  their required submission; if so it advances `app_state.state`.
  """
  username = session.get("username")
  if not username:
    return jsonify({"error": "not authenticated"}), 403

  data = request.get_json(silent=True) or request.form

  with USERS_LOCK:
    user = usersdb.get(username)
    if user is None:
      return jsonify({"error": "user not found"}), 404
    role = user.state

  # Handle by role
  if role is UserState.PLAYER:
    text = data.get("text") if hasattr(data, "get") else None
    if text is None:
      return jsonify({"error": "text is required for player submissions"}), 400
    with USERS_LOCK:
      user = usersdb.get(username)
      user.text = str(text)
    saved_value = user.text

  elif role is UserState.READER:
    word = data.get("word") if hasattr(data, "get") else None
    text = data.get("text") if hasattr(data, "get") else None
    if not word or not text:
      return jsonify({"error": "word and text is required for reader submissions"}), 400
    with USERS_LOCK:
      user = usersdb.get(username)
      user.text = str(text)
      saved_value = user.text
    with STATE_LOCK:
      app_state.word = str(word or "")

  else:
    return jsonify({"error": "user not in a valid role for submissions"}), 400

  # After saving, check whether all users have submitted
  move_to_reading = False
  with USERS_LOCK:
    all_submitted = True
    for u in usersdb.values():
      if u.state is UserState.PLAYER:
        if not (u.text and str(u.text).strip()):
          all_submitted = False
          break
      elif u.state is UserState.READER:
        with STATE_LOCK:
          if not (app_state.word and str(app_state.word).strip()):
            all_submitted = False
            break
    if all_submitted:
      with STATE_LOCK:
        app_state.state = GameState.GAME_WAITING_FOR_DECISION_IRL
      move_to_reading = True

  return jsonify({"ok": True, "value": saved_value, "move": move_to_reading})


if __name__ == "__main__":
  app.run(debug=True)
