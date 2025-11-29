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


def init():
  pass


#     # In-memory storage for usernames while the server is running
#     global usersdb: Dict[str, UserInfo] = {}
#     global USERS_LOCK = Lock()

#     # Global application state
#     global app_state = AppState()
#     global STATE_LOCK = Lock()
