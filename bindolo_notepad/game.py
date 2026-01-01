from flask import (
  Blueprint,
  render_template,
  request,
  redirect,
  url_for,
  jsonify,
  session,
)
import random
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
  check_readiness,
)


bp = Blueprint("game", __name__, url_prefix="/game")


@bp.route("/", methods=["POST", "GET"])
def landing():
  reason = None
  user_state = None
  accepted = False
  if request.method == "POST":
    username = request.form.get("username", "").strip()
    if not username:
      return redirect(url_for("index"))

    # Only allow new users while the app is waiting for players
    with STATE_LOCK:
      current_state = app_state.state

    if current_state is not GameState.WAITING_FOR_NEW_PLAYERS:
      # registration closed — show informative landing with rejection
      accepted = False
      reason = (
        "La partita è già iniziata. Non si possono più aggiungere nuovi giocatori."
      )
    else:
      accepted = True
      # register user in-memory
      with USERS_LOCK:
        info = usersdb.get(username)
        if info is None:
          info = UserInfo()
          usersdb[username] = info

        # persist username in session so subsequent pages know which user this is
        session["username"] = username
  else:
    # If the user has a session username, show the landing view for them.
    username = session.get("username")
    if not username:
      return redirect(url_for("index"))

    with USERS_LOCK:
      info = usersdb.get(username)
      if info is None:
        return redirect(url_for("index"))
    user_state = info.state.value
    accepted = True
  return render_template(
    "game/landing.html",
    username=username,
    accepted=accepted,
    reason=reason,
    user_state=user_state,
  )


@bp.route("/user/ready", methods=["POST"])
def set_user_ready():
  # Accept JSON or form data with `username`
  data = request.get_json(silent=True) or request.form
  username = data.get("username") if hasattr(data, "get") else None
  if not username:
    return jsonify({"error": "username is required"}), 400

  with USERS_LOCK:
    user = usersdb.get(username)
    if user is None:
      return jsonify({"error": "user not found"}), 404
    user.state = UserState.READY
  check_readiness()
  # return the new state and whether the game has started
  with STATE_LOCK:
    started_flag = app_state.state != GameState.WAITING_FOR_NEW_PLAYERS

  return jsonify(
    {"username": username, "state": user.state.value, "started": started_flag}
  )


@bp.route("/play", methods=["GET"])
def play():
  # Simple play page: determine username from session and pass user's state
  username = session.get("username")
  user_state = None
  if username:
    with USERS_LOCK:
      user = usersdb.get(username)
      if user is not None:
        user_state = user.state.value

  return render_template("game/play.html", username=username, user_state=user_state)


@bp.route("/reading", methods=["GET"])
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
    player_texts = []
    # If the current session user is the reader, present player texts in a random order
    if user_state == UserState.READER.value:
      player_texts = [
        {"text": u.text}
        for _, u in usersdb.items()
        if (u.text is not None and u.text != "")
      ]
      random.shuffle(player_texts)
  with STATE_LOCK:
    word = app_state.word

  return render_template(
    "game/reading.html",
    username=username,
    user_state=user_state,
    game_word=word,
    player_texts=player_texts,
  )


@bp.route("/reading/restart", methods=["POST"])
def reading_restart():
  # Only the current reader may trigger a restart
  username = session.get("username")
  if not username:
    return jsonify({"error": "not authenticated"}), 403

  with USERS_LOCK:
    user = usersdb.get(username)
    if user is None:
      return jsonify({"error": "user not found"}), 404
    if user.state is not UserState.READER:
      return jsonify({"error": "only the reader may restart the round"}), 403

  # Reset global state and per-user states
  with STATE_LOCK:
    app_state.state = GameState.WAITING_FOR_PLAYERS
    app_state.word = None

  with USERS_LOCK:
    for u in usersdb.values():
      u.state = UserState.ENTERING
      u.text = ""

  return jsonify({"ok": True})


@bp.route("/play/submit", methods=["POST"])
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

  return jsonify(
    {
      "ok": True,
      "value": saved_value,
      "move": move_to_reading,
    }
  )
