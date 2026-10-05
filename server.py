"""Steer multiplayer server — lobby + state relay over WebSockets.

Single process handles plenty (7-10 lobbies = ~120 sockets is trivial for asyncio). To scale
horizontally across several replicas (e.g. on Render), set REDIS_URL: rooms are then shared
through Redis so a player can join a lobby hosted on any instance.

Model when Redis is on: the instance a lobby is *created* on OWNS it (holds the room object +
all game logic). Other instances are thin edges that pipe their local client's frames to the
owner over a Redis pub/sub bus, and deliver the owner's outbound frames back to their sockets.
A Redis registry (steer:owner:<code> -> instance id) lets any instance find a lobby's owner.
Without REDIS_URL everything stays in-process and behaves exactly as before.

Deploy target: Render Web Service (binds 0.0.0.0:$PORT). Run locally: PORT=8765 python server.py
"""
import asyncio
import http
import json
import os
import random
import string
import uuid

import websockets

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

INST = uuid.uuid4().hex[:8]         # this instance's id
CODE_CHARS = string.ascii_uppercase + string.digits
REDIS_URL = os.environ.get("REDIS_URL")
ROOM_TTL = 3600                     # seconds a room registry entry lives (refreshed on change)

ROOMS = {}                          # code -> Room (only on the owning instance)
LOCAL_WS = {}                       # cid -> websocket (this instance's own sockets)
REDIS = None                        # redis client, or None for in-memory mode


def new_code():
    return "".join(random.choice(CODE_CHARS) for _ in range(6))


# =====================================================================================
# the message bus: deliver a frame to a player (local socket or another instance)
# =====================================================================================
async def bus_publish(inst, obj):
    if REDIS is not None:
        await REDIS.publish(f"steer:inst:{inst}", json.dumps(obj))


async def send_to_cid(cid, data):
    ws = LOCAL_WS.get(cid)
    if ws is not None:
        try:
            await ws.send(json.dumps(data))
        except Exception:
            pass


async def close_cid(cid):
    ws = LOCAL_WS.get(cid)
    if ws is not None:
        try:
            await ws.close()
        except Exception:
            pass


# =====================================================================================
# rooms
# =====================================================================================
class Player:
    __slots__ = ("id", "inst", "cid", "name", "flag", "ready", "slot")

    def __init__(self, pid, inst, cid, name, flag):
        self.id = pid
        self.inst = inst            # instance holding this player's socket
        self.cid = cid              # that instance's connection id
        self.name = (name or "Player")[:12] or "Player"
        self.flag = flag
        self.ready = False
        self.slot = None


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


class Room:
    def __init__(self, code, host_name, maxp, settings=None):
        self.code = code
        self.host_id = None
        self.max = max(2, min(12, maxp))
        self.started = False
        self.seed = None
        self.players = {}
        self.next_id = 1
        self.name = host_name
        self.banned_names = set()
        self.settings = dict(DEFAULT_ROOM_SETTINGS)
        if isinstance(settings, dict):
            self.settings.update(settings)

    def add(self, inst, cid, name, flag):
        pid = self.next_id
        self.next_id += 1
        p = Player(pid, inst, cid, name, flag)
        self.players[pid] = p
        if self.host_id is None:
            self.host_id = pid
            self.name = p.name
        return p

    def room_msg(self):
        return {
            "t": "room", "code": self.code, "name": self.name, "host": self.host_id,
            "max": self.max, "started": self.started,
            "settings": self.settings,
            "players": [{"id": p.id, "name": p.name, "flag": p.flag, "ready": p.ready}
                        for p in self.players.values()],
        }

    def all_ready(self):
        ps = list(self.players.values())
        return len(ps) >= 2 and all(p.ready for p in ps)


async def send_player(p, obj):
    if p.inst == INST:
        await send_to_cid(p.cid, obj)
    else:
        await bus_publish(p.inst, {"t": "deliver", "cid": p.cid, "data": obj})


async def close_player(p):
    if p.inst == INST:
        await close_cid(p.cid)
    else:
        await bus_publish(p.inst, {"t": "close", "cid": p.cid})


async def broadcast(room, obj, exclude_pid=None):
    for p in list(room.players.values()):
        if p.id != exclude_pid:
            await send_player(p, obj)


async def cache_room(room):
    # cache a small lobby summary in Redis (handy for a lobby list / monitoring)
    if REDIS is None:
        return
    await REDIS.set(f"steer:room:{room.code}",
                    json.dumps({"name": room.name, "players": len(room.players),
                                "max": room.max, "started": room.started,
                                "settings": room.settings}),
                    ex=ROOM_TTL)
    await REDIS.set(f"steer:owner:{room.code}", INST, ex=ROOM_TTL)


async def drop_room(code):
    ROOMS.pop(code, None)
    if REDIS is not None:
        await REDIS.delete(f"steer:room:{code}", f"steer:owner:{code}")


async def start_race(room):
    room.started = True
    room.seed = random.randint(0, 1_000_000)
    for slot, p in enumerate(room.players.values()):
        p.slot = slot
    players = [{"id": p.id, "name": p.name, "flag": p.flag, "slot": p.slot}
               for p in room.players.values()]
    await broadcast(room, {"t": "start", "seed": room.seed, "players": players, "settings": room.settings})
    await cache_room(room)


async def find_owner(code):
    if code in ROOMS:
        return INST
    if REDIS is not None:
        owner = await REDIS.get(f"steer:owner:{code}")
        return owner.decode() if isinstance(owner, bytes) else owner
    return None


# =====================================================================================
# authoritative handling (runs on the owner instance)
# =====================================================================================
async def owner_add_player(code, inst, cid, name, flag):
    room = ROOMS.get(code)
    if room is None:
        await send_one(inst, cid, {"t": "err", "msg": "No room with that code"})
        return
    if name and name.lower() in getattr(room, "banned_names", set()):
        await send_one(inst, cid, {"t": "err", "msg": "You are banned from this room"})
        return
    if room.started:
        await send_one(inst, cid, {"t": "err", "msg": "Race already started"})
        return
    if len(room.players) >= room.max:
        await send_one(inst, cid, {"t": "err", "msg": "Room is full"})
        return
    p = room.add(inst, cid, name, flag)
    await send_one(inst, cid, {**room.room_msg(), "self": p.id})
    await broadcast(room, room.room_msg())
    await cache_room(room)
    if room.all_ready() and not room.started:
        await start_race(room)


async def send_one(inst, cid, obj):
    if inst == INST:
        await send_to_cid(cid, obj)
    else:
        await bus_publish(inst, {"t": "deliver", "cid": cid, "data": obj})


def player_by_cid(room, inst, cid):
    for p in room.players.values():
        if p.inst == inst and p.cid == cid:
            return p
    return None


async def owner_handle_frame(code, inst, cid, msg):
    room = ROOMS.get(code)
    if room is None:
        return
    me = player_by_cid(room, inst, cid)
    if me is None:
        return
    t = msg.get("t")
    if t == "ready":
        me.ready = bool(msg.get("v"))
        await broadcast(room, room.room_msg())
        await cache_room(room)
        if room.all_ready() and not room.started:
            await start_race(room)
    elif t in ("kick", "ban") and me.id == room.host_id:
        target = room.players.get(int(msg.get("id", -1)))
        if target and target.id != room.host_id:
            if t == "ban":
                room.banned_names.add(target.name.lower())
            await send_player(target, {"t": "kicked" if t == "kick" else "banned"})
            await close_player(target)
    elif t == "settings" and me.id == room.host_id:
        st = msg.get("settings")
        if isinstance(st, dict):
            for k in ("bot_aggression", "laps", "bot_count", "track", "rotation",
                      "collision", "privacy", "slipstream", "items"):
                if k in st:
                    room.settings[k] = st[k]
            await broadcast(room, room.room_msg())
            await cache_room(room)
    elif t in ("state", "box", "bots", "finished"):
        if t in ("box", "bots", "finished") and me.id != room.host_id:
            return                              # only the host is authoritative
        await broadcast(room, {**msg, "id": me.id}, exclude_pid=me.id)


async def owner_remove_player(code, inst, cid):
    room = ROOMS.get(code)
    if room is None:
        return
    me = player_by_cid(room, inst, cid)
    if me is None:
        return
    room.players.pop(me.id, None)
    if not room.players:
        await drop_room(code)
        return
    if me.id == room.host_id:
        room.host_id = next(iter(room.players))     # promote a new host
        room.name = room.players[room.host_id].name
    await broadcast(room, {"t": "left", "id": me.id})
    await broadcast(room, room.room_msg())
    await cache_room(room)
    if room.all_ready() and not room.started:
        await start_race(room)


# =====================================================================================
# per-connection handler (runs on whichever instance the client connected to)
# =====================================================================================
async def handler(ws):
    cid = uuid.uuid4().hex
    LOCAL_WS[cid] = ws
    code = None
    owner = None
    try:
        # a dropped/half-open socket raises ConnectionClosed from the iterator itself;
        # that's a normal disconnect, not a handler failure, so swallow it quietly
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            t = msg.get("t")

            if code is None:
                if t == "host":
                    code = new_code()
                    while code in ROOMS or await find_owner(code):
                        code = new_code()
                    ROOMS[code] = Room(code, msg.get("name", "Player"), int(msg.get("max", 4)),
                                       settings=msg.get("settings"))
                    owner = INST
                    p = ROOMS[code].add(INST, cid, msg.get("name", "Player"), msg.get("flag"))
                    await send_to_cid(cid, {**ROOMS[code].room_msg(), "self": p.id})
                    await cache_room(ROOMS[code])
                elif t == "join":
                    target = str(msg.get("code", "")).upper().strip()
                    owner = await find_owner(target)
                    if owner is None:
                        await send_to_cid(cid, {"t": "err", "msg": "No room with that code"})
                        continue
                    code = target
                    if owner == INST:
                        await owner_add_player(code, INST, cid, msg.get("name"), msg.get("flag"))
                    else:
                        await bus_publish(owner, {"t": "edge_join", "code": code, "inst": INST,
                                                  "cid": cid, "name": msg.get("name"),
                                                  "flag": msg.get("flag")})
                continue

            # subsequent frames: handle on the owner (locally or via the bus)
            if owner == INST:
                await owner_handle_frame(code, INST, cid, msg)
            else:
                await bus_publish(owner, {"t": "edge_frame", "code": code, "inst": INST,
                                          "cid": cid, "msg": msg})
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        LOCAL_WS.pop(cid, None)
        if code is not None and owner is not None:
            if owner == INST:
                await owner_remove_player(code, INST, cid)
            else:
                await bus_publish(owner, {"t": "edge_leave", "code": code, "inst": INST, "cid": cid})


# =====================================================================================
# Redis subscriber: routes bus messages for this instance
# =====================================================================================
async def bus_listener():
    if REDIS is None:
        return
    pubsub = REDIS.pubsub()
    await pubsub.subscribe(f"steer:inst:{INST}")
    async for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        try:
            obj = json.loads(message["data"])
        except (ValueError, TypeError, KeyError):
            continue
        # one bad message must not kill this loop: it's the only thing routing cross-instance
        # traffic, and if it dies this instance silently stops serving shared lobbies
        try:
            t = obj.get("t")
            if t == "deliver":                      # edge: send to a local socket
                await send_to_cid(obj["cid"], obj["data"])
            elif t == "close":
                await close_cid(obj["cid"])
            elif t == "edge_join":                  # owner: a client joined via another instance
                await owner_add_player(obj["code"], obj["inst"], obj["cid"], obj.get("name"), obj.get("flag"))
            elif t == "edge_frame":
                await owner_handle_frame(obj["code"], obj["inst"], obj["cid"], obj["msg"])
            elif t == "edge_leave":
                await owner_remove_player(obj["code"], obj["inst"], obj["cid"])
        except Exception as e:
            print("bus message failed, skipped:", type(e).__name__, e)


# =====================================================================================
# bootstrap
# =====================================================================================
def health_check(connection, request):
    if request.headers.get("Upgrade", "").lower() != "websocket":
        return connection.respond(http.HTTPStatus.OK, "Steer server up\n")
    return None


async def main():
    global REDIS
    if REDIS_URL and aioredis is not None:
        REDIS = aioredis.from_url(REDIS_URL)
        try:
            await REDIS.ping()
            print(f"Redis connected ({REDIS_URL}); instance {INST}")
            asyncio.ensure_future(bus_listener())
        except Exception as e:
            print("Redis unavailable, falling back to in-memory:", e)
            REDIS = None
    port = int(os.environ.get("PORT", 8765))
    print(f"Steer server listening on 0.0.0.0:{port} (instance {INST}, "
          f"{'redis' if REDIS else 'in-memory'})")
    async with websockets.serve(handler, "0.0.0.0", port, ping_interval=20,
                                process_request=health_check):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
