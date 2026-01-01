from threading import Lock
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any


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
  WAITING_FOR_NEW_PLAYERS = "waiting_for_new_players"
  WAITING_FOR_PLAYERS = "waiting_for_players"
  GAME_WAITING_FOR_DEFINITIONS = "game_waiting_for_definitions"
  GAME_WAITING_FOR_DECISION_IRL = "game_waiting_for_decision_irl"


@dataclass
class AppState:
  """Global application state held in-memory while the process runs."""

  state: GameState = GameState.WAITING_FOR_NEW_PLAYERS
  info: Dict[str, Any] | None = None
  word: str | None = None
  # rotation order for selecting the reader and next index
  reader_order: list[str] | None = None
  reader_idx: int = 0


usersdb: Dict[str, UserInfo] = {}
USERS_LOCK = Lock()
app_state = AppState()
STATE_LOCK = Lock()


def check_readiness():
  with USERS_LOCK:
    total = len(usersdb)
    necessary_players = total >= MINIMUM_PLAYERS
    all_ready = total > 0 and all(v.state is UserState.READY for v in usersdb.values())

  # If all are ready and we've reached the minimum players, mark the game started
  if necessary_players and all_ready:
    with STATE_LOCK:
      if (
        app_state.state is GameState.WAITING_FOR_PLAYERS
        or app_state.state is GameState.WAITING_FOR_NEW_PLAYERS
      ):
        # now we do not accept any new user
        if app_state.state is GameState.WAITING_FOR_NEW_PLAYERS:
          with USERS_LOCK:
            app_state.reader_order = list(usersdb.keys())
            app_state.reader_idx = 0
        app_state.state = GameState.GAME_WAITING_FOR_DEFINITIONS
        assert app_state.reader_order is not None
        assert app_state.reader_idx is not None
        # choose the next reader based on the rotation index

        idx = app_state.reader_idx % len(app_state.reader_order)
        reader = app_state.reader_order[idx]
        app_state.reader_idx = (idx + 1) % len(app_state.reader_order)

        # Assign roles accordingly
        with USERS_LOCK:
          for uname, u in usersdb.items():
            if uname == reader:
              u.state = UserState.READER
            else:
              u.state = UserState.PLAYER


def init():
  pass


#     # In-memory storage for usernames while the server is running
#     global usersdb: Dict[str, UserInfo] = {}
#     global USERS_LOCK = Lock()

#     # Global application state
#     global app_state = AppState()
#     global STATE_LOCK = Lock()
