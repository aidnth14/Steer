"""Steer multiplayer server — a lightweight lobby + state relay over WebSockets.

Deploy target: Render (a Web Service). Render sets $PORT; we bind 0.0.0.0:$PORT.
Run locally with:  PORT=8765 python server.py

Model: the server owns rooms (lobbies). Each player runs the game and simulates its
own car, broadcasting its state ~20x/s; the server relays those snapshots to the rest
of the room. No heavy physics on the server, so it stays cheap and scales fine.

Protocol is newline-free JSON text frames. See README for the message list.
"""
import asyncio
import http
import json
import os
import random
import string

import websockets

ROOMS = {}          # code -> Room
CODE_CHARS = string.ascii_uppercase + string.digits


def new_code():
    while True:
        code = "".join(random.choice(CODE_CHARS) for _ in range(6))
        if code not in ROOMS:
            return code


class Player:
    __slots__ = ("id", "ws", "name", "flag", "ready", "slot")

    def __init__(self, pid, ws, name, flag):
        self.id = pid
        self.ws = ws
        self.name = name[:12] or "Player"
        self.flag = flag
        self.ready = False
        self.slot = None


class Room:
    def __init__(self, code, host_name, maxp):
        self.code = code
        self.host_id = None
        self.max = max(2, min(12, maxp))
        self.started = False
        self.seed = None
        self.players = {}       # id -> Player
        self.next_id = 1
        self.name = host_name    # lobby name = host's name

    def add(self, ws, name, flag):
        pid = self.next_id
        self.next_id += 1
        p = Player(pid, ws, name, flag)
        self.players[pid] = p
        if self.host_id is None:
            self.host_id = pid
            self.name = p.name
        return p

    def room_msg(self):
        return {
            "t": "room",
            "code": self.code,
            "name": self.name,
            "host": self.host_id,
            "max": self.max,
            "started": self.started,
            "players": [
                {"id": p.id, "name": p.name, "flag": p.flag, "ready": p.ready}
                for p in self.players.values()
            ],
        }

    def all_ready(self):
        ps = list(self.players.values())
        return len(ps) >= 2 and all(p.ready for p in ps)


async def send(ws, obj):
    try:
        await ws.send(json.dumps(obj))
    except Exception:
        pass


async def broadcast(room, obj, exclude=None):
    data = json.dumps(obj)
    for p in list(room.players.values()):
        if p.ws is exclude:
            continue
        try:
            await p.ws.send(data)
        except Exception:
            pass


async def broadcast_room(room):
    await broadcast(room, room.room_msg())


async def start_race(room):
    room.started = True
    room.seed = random.randint(0, 1_000_000)
    for slot, p in enumerate(room.players.values()):
        p.slot = slot
    players = [{"id": p.id, "name": p.name, "flag": p.flag, "slot": p.slot}
               for p in room.players.values()]
    await broadcast(room, {"t": "start", "seed": room.seed, "players": players})


async def handler(ws):
    room = None
    me = None
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            t = msg.get("t")

            if t == "host" and room is None:
                code = new_code()
                room = Room(code, msg.get("name", "Player"), int(msg.get("max", 4)))
                ROOMS[code] = room
                me = room.add(ws, msg.get("name", "Player"), msg.get("flag"))
                await send(ws, {**room.room_msg(), "self": me.id})

            elif t == "join" and room is None:
                code = str(msg.get("code", "")).upper().strip()
                r = ROOMS.get(code)
                if r is None:
                    await send(ws, {"t": "err", "msg": "No room with that code"})
                elif r.started:
                    await send(ws, {"t": "err", "msg": "Race already started"})
                elif len(r.players) >= r.max:
                    await send(ws, {"t": "err", "msg": "Room is full"})
                else:
                    room = r
                    me = room.add(ws, msg.get("name", "Player"), msg.get("flag"))
                    await send(ws, {**room.room_msg(), "self": me.id})
                    await broadcast_room(room)

            elif room is None or me is None:
                continue        # everything below needs to be in a room

            elif t == "ready":
                me.ready = bool(msg.get("v"))
                await broadcast_room(room)
                if room.all_ready() and not room.started:
                    await start_race(room)

            elif t == "kick" and me.id == room.host_id:
                target = room.players.get(int(msg.get("id", -1)))
                if target and target.id != room.host_id:
                    await send(target.ws, {"t": "kicked"})
                    try:
                        await target.ws.close()
                    except Exception:
                        pass

            elif t in ("state", "box", "bots", "finished"):
                # in-race traffic: relay to the rest of the room, tagged with the sender id
                await broadcast(room, {**msg, "id": me.id}, exclude=ws)
    finally:
        if room is not None and me is not None:
            room.players.pop(me.id, None)
            if not room.players:
                ROOMS.pop(room.code, None)
            else:
                if me.id == room.host_id:
                    room.host_id = next(iter(room.players))     # promote a new host
                    room.name = room.players[room.host_id].name
                await broadcast(room, {"t": "left", "id": me.id})
                await broadcast_room(room)
                if room.all_ready() and not room.started:
                    await start_race(room)


def health_check(connection, request):
    # Render (and other hosts) hit "/" with a plain HTTP GET; answer 200 unless this is
    # actually a WebSocket upgrade, which we let through to the handler.
    if request.headers.get("Upgrade", "").lower() != "websocket":
        return connection.respond(http.HTTPStatus.OK, "Steer server up\n")
    return None


async def main():
    port = int(os.environ.get("PORT", 8765))
    print(f"Steer server listening on 0.0.0.0:{port}")
    async with websockets.serve(handler, "0.0.0.0", port, ping_interval=20,
                                process_request=health_check):
        await asyncio.Future()     # run forever


if __name__ == "__main__":
    asyncio.run(main())
