from flask import Flask, render_template, jsonify, session
import os
from .state import (
  # global variables
  app_state,
  usersdb,
  # types
  GameState,
  UserState,
  UserInfo,
  # locks
  USERS_LOCK,
  STATE_LOCK,
  # parameters
  MINIMUM_PLAYERS,
)


def create_app(test_config=None):
  app = Flask(__name__, instance_relative_config=True)
  app.config.from_mapping(
    SECRET_KEY="dev-secret",
  )
  from .state import init as init_state

  init_state()
  # Convenience: add two fake users for quick local testing when the
  # environment variable `BINDOLO_FAKE_USERS=1` is set. This is temporary
  # and safe for development — it won't run unless you set the env var.
  if os.getenv("BINDOLO_FAKE_USERS") == "1":
    with USERS_LOCK:
      usersdb.setdefault("Antonietta", UserInfo())
      usersdb.setdefault("Bromualdo", UserInfo())

  @app.route("/", methods=["GET"])
  def index():
    session.clear()
    # TODO: reset the session here
    # pass the current mapping of stored usernames to the template
    with USERS_LOCK:
      current = {
        k: {"state": v.state.value, "text": v.text} for k, v in usersdb.items()
      }
    with STATE_LOCK:
      current_state = app_state.state.value
    return render_template("index.html", usersdb=current, state=current_state)

  @app.route("/usersdb", methods=["GET"])
  def get_users():
    # return simple status booleans used by the landing page polling JS
    # - `necessary_players`: true when we have at least the minimum number of players
    # - `all_ready`: true when there is at least one user and every user is in the READY state
    with USERS_LOCK:
      total = len(usersdb)
      necessary_players = total >= MINIMUM_PLAYERS
      # the all ready might need to be tweaked a bit: I do not thing it is robust to rely only on ENTERING here
      all_ready = total > 0 and all(
        v.state is not UserState.ENTERING for v in usersdb.values()
      )
      return jsonify({"necessary_players": necessary_players, "all_ready": all_ready})

  @app.route("/players", methods=["GET"])
  def get_players():
    # return a simple mapping of username -> state (no text)
    with USERS_LOCK:
      return jsonify({"users": {k: v.state.value for k, v in usersdb.items()}})

  @app.route("/state", methods=["GET"])
  def get_state():
    with STATE_LOCK:
      return jsonify(
        {
          "state": app_state.state.value,
          "info": app_state.info or {},
          "started": app_state.state != GameState.WAITING_FOR_NEW_PLAYERS,
          "word": app_state.word,
        }
      )

  # @app.route("/clear", methods=["POST"])
  # def clear_users():
  #   # clear the in-memory storage
  #   with USERS_LOCK:
  #     usersdb.clear()
  #   return redirect(url_for("index"))

  @app.route("/admin", methods=["GET"])
  def admin():
    return render_template("admin.html")

  # now loading the game logic
  from . import game

  app.register_blueprint(game.bp)

  return app


app = create_app()
if __name__ == "__main__":
  app.run(debug=True)
