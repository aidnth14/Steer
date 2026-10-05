"""In-process lobby/room state, ported from steer/server.py's Room/Player classes.

Channels groups handle the cross-connection broadcast (what server.py needed its own Redis pub/sub
"bus" for, since raw asyncio websockets has no built-in group primitive) -- so this is simpler than
server.py: no inst/cid/bus_publish indirection, just room code -> Room, keyed by Channels'
per-connection channel_name instead of a cid.

Caveat carried over from server.py's own docs: this dict lives in ONE process's memory. Fine for
dev/single-worker (matches server.py without REDIS_URL). Scaling to multiple ASGI workers needs
room state moved to a shared store (Redis), not just the channel layer -- same tradeoff server.py
documents for its own Redis mode.
"""
import random
import string

CODE_CHARS = string.ascii_uppercase + string.digits

DEFAULT_ROOM_SETTINGS = {
    "bot_aggression": "Casual",
    "laps": 3,
    "bot_count": "fill",
    "track": "meadow_dirt",
    "rotation": "Host Choice",
    "collision": "Full Contact",
    "privacy": "Public",
    "slipstream": "ON",
    "items": "Standard",
}

SETTINGS_KEYS = tuple(DEFAULT_ROOM_SETTINGS.keys())

ROOMS: dict[str, "Room"] = {}


def new_code() -> str:
    code = "".join(random.choice(CODE_CHARS) for _ in range(6))
    while code in ROOMS:
        code = "".join(random.choice(CODE_CHARS) for _ in range(6))
    return code


class Player:
    __slots__ = ("id", "channel_name", "name", "flag", "ready", "slot")

    def __init__(self, pid, channel_name, name, flag):
        self.id = pid
        self.channel_name = channel_name
        self.name = (name or "Player")[:12] or "Player"
        self.flag = flag
        self.ready = False
        self.slot = None


class Room:
    def __init__(self, code, host_name, maxp, settings=None):
        self.code = code
        self.host_id = None
        self.max = max(2, min(12, maxp))
        self.started = False
        self.seed = None
        self.players: dict[int, Player] = {}
        self.next_id = 1
        self.name = host_name
        self.banned_names: set[str] = set()
        self.settings = dict(DEFAULT_ROOM_SETTINGS)
        if isinstance(settings, dict):
            self.settings.update({k: v for k, v in settings.items() if k in SETTINGS_KEYS})

    def add(self, channel_name, name, flag) -> Player:
        pid = self.next_id
        self.next_id += 1
        p = Player(pid, channel_name, name, flag)
        self.players[pid] = p
        if self.host_id is None:
            self.host_id = pid
            self.name = p.name
        return p

    def player_by_channel(self, channel_name) -> Player | None:
        for p in self.players.values():
            if p.channel_name == channel_name:
                return p
        return None

    def room_msg(self) -> dict:
        return {
            "t": "room", "code": self.code, "name": self.name, "host": self.host_id,
            "max": self.max, "started": self.started, "settings": self.settings,
            "players": [{"id": p.id, "name": p.name, "flag": p.flag, "ready": p.ready}
                        for p in self.players.values()],
        }

    def all_ready(self) -> bool:
        ps = list(self.players.values())
        return len(ps) >= 2 and all(p.ready for p in ps)

    def start(self):
        self.started = True
        self.seed = random.randint(0, 1_000_000)
        for slot, p in enumerate(self.players.values()):
            p.slot = slot
