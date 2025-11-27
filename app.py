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

  return render_template("landing.html", username=username, accepted=True)


@app.route("/usersdb", methods=["GET"])
def get_users():
  # return JSON mapping of username -> info
  with USERS_LOCK:
    return jsonify({k: {"state": v.state.value, "text": v.text} for k, v in usersdb.items()})


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


if __name__ == "__main__":
  app.run(debug=True)
