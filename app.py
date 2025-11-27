from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any

from flask import Flask, render_template, request, redirect, url_for, jsonify
from threading import Lock

app = Flask(__name__)


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


# In-memory storage for usernames while the server is running
usersdb: Dict[str, UserInfo] = {}
USERS_LOCK = Lock()

# Global application state
app_state = AppState()
STATE_LOCK = Lock()


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

  if current_state is not GameState.WAITING_FOR_PLAYERS:
    # registration closed — show informative landing with rejection
    reason = f"Registration is closed (state={current_state.value})."
    return render_template("landing.html", username=username, accepted=False, reason=reason)

  # register user in-memory (no counter)
  with USERS_LOCK:
    info = usersdb.get(username)
    if info is None:
      info = UserInfo()
      usersdb[username] = info

  return render_template("landing.html", username=username, accepted=True, user_state=info.state.value)


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

  return jsonify({"username": username, "state": user.state.value})


@app.route("/usersdb", methods=["GET"])
def get_users():
  # return simple status booleans used by the landing page polling JS
  # - `necessary_players`: true when we have at least the minimum number of players
  # - `all_ready`: true when there is at least one user and every user is in the READY state
  with USERS_LOCK:
    total = len(usersdb)
    necessary_players = total >= 3
    all_ready = total > 0 and all(v.state is UserState.READY for v in usersdb.values())
    return jsonify({"necessary_players": necessary_players, "all_ready": all_ready})


@app.route("/players", methods=["GET"])
def get_players():
  # return a simple mapping of username -> state (no text)
  with USERS_LOCK:
    return jsonify({k: v.state.value for k, v in usersdb.items()})


@app.route("/state", methods=["GET"])
def get_state():
  with STATE_LOCK:
    return jsonify({"state": app_state.state.value, "info": app_state.info or {}})


@app.route("/clear", methods=["POST"])
def clear_users():
  # clear the in-memory storage
  with USERS_LOCK:
    usersdb.clear()
  return redirect(url_for("index"))


@app.route("/admin", methods=["GET"])
def admin():
  return render_template('admin.html')


@app.route("/play", methods=["GET"])
def play():
  # Simple play page with a text box and submit button (no backend handling)
  return render_template('play.html')


if __name__ == "__main__":
  app.run(debug=True)
