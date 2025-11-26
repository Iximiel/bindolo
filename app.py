from dataclasses import dataclass
from typing import Dict

from flask import Flask, render_template, request, redirect, url_for, jsonify
from threading import Lock

app = Flask(__name__)


@dataclass
class UserInfo:
  """In-memory info stored per user while the server runs."""

  count: int = 0


# In-memory storage for usernames while the server is running
usersdb: Dict[str, UserInfo] = {}
USERS_LOCK = Lock()


@app.route("/", methods=["GET"])
def index():
  # pass the current mapping of stored usernames to the template
  with USERS_LOCK:
    current = dict(usersdb)
  return render_template("index.html", usersdb=current)


@app.route("/landing", methods=["POST"])
def landing():
  username = request.form.get("username", "").strip()
  if not username:
    return redirect(url_for("index"))

  # increment insertion count for this username
  with USERS_LOCK:
    info = usersdb.get(username)
    if info is None:
      info = UserInfo(count=1)
      usersdb[username] = info
    else:
      info.count += 1

  return render_template("landing.html", username=username)


@app.route("/usersdb", methods=["GET"])
def get_users():
  # return JSON mapping of username -> insertion count
  with USERS_LOCK:
    return jsonify({k: v.count for k, v in usersdb.items()})


@app.route("/clear", methods=["POST"])
def clear_users():
  # clear the in-memory storage
  with USERS_LOCK:
    usersdb.clear()
  return redirect(url_for("index"))


if __name__ == "__main__":
  app.run(debug=True)
