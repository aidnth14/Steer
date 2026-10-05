"""WebSocket lobby/relay consumer, ported from steer/server.py's handler()/owner_* functions.

Wire protocol is kept identical to server.py's (same {"t": ...} message shapes) so the two
backends are drop-in compatible with the same client-side expectations.
"""
import json

from channels.generic.websocket import AsyncWebsocketConsumer

from .rooms import ROOMS, Room, SETTINGS_KEYS, new_code


def group_name(code: str) -> str:
    return f"room_{code}"


class LobbyConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.code = None
        await self.accept()

    async def disconnect(self, close_code):
        if self.code is None:
            return
        room = ROOMS.get(self.code)
        if room is None:
            return
        me = room.player_by_channel(self.channel_name)
        if me is None:
            return
        await self.channel_layer.group_discard(group_name(self.code), self.channel_name)
        room.players.pop(me.id, None)
        if not room.players:
            ROOMS.pop(self.code, None)
            return
        if me.id == room.host_id:
            room.host_id = next(iter(room.players))
            room.name = room.players[room.host_id].name
        await self.group_broadcast({"t": "left", "id": me.id})
        await self.group_broadcast(room.room_msg())
        if room.all_ready() and not room.started:
            await self.start_race(room)

    async def receive(self, text_data=None, bytes_data=None):
        if text_data is None:
            return
        try:
            msg = json.loads(text_data)
        except (ValueError, TypeError):
            return
        t = msg.get("t")

        if self.code is None:
            if t == "host":
                await self.handle_host(msg)
            elif t == "join":
                await self.handle_join(msg)
            return

        room = ROOMS.get(self.code)
        if room is None:
            return
        me = room.player_by_channel(self.channel_name)
        if me is None:
            return

        if t == "ready":
            me.ready = bool(msg.get("v"))
            await self.group_broadcast(room.room_msg())
            if room.all_ready() and not room.started:
                await self.start_race(room)
        elif t in ("kick", "ban") and me.id == room.host_id:
            target = room.players.get(int(msg.get("id", -1)))
            if target and target.id != room.host_id:
                if t == "ban":
                    room.banned_names.add(target.name.lower())
                await self.channel_layer.send(
                    target.channel_name, {"type": "deliver", "data": {"t": "kicked" if t == "kick" else "banned"}}
                )
                await self.channel_layer.send(target.channel_name, {"type": "force_close"})
        elif t == "settings" and me.id == room.host_id:
            st = msg.get("settings")
            if isinstance(st, dict):
                for k in SETTINGS_KEYS:
                    if k in st:
                        room.settings[k] = st[k]
                await self.group_broadcast(room.room_msg())
        elif t in ("state", "box", "bots", "finished"):
            if t in ("box", "bots", "finished") and me.id != room.host_id:
                return  # only the host is authoritative
            await self.group_broadcast({**msg, "id": me.id}, exclude_channel=self.channel_name)

    # ---- host / join -----------------------------------------------------------------
    async def handle_host(self, msg):
        code = new_code()
        room = Room(code, msg.get("name", "Player"), int(msg.get("max", 4)), settings=msg.get("settings"))
        ROOMS[code] = room
        self.code = code
        p = room.add(self.channel_name, msg.get("name", "Player"), msg.get("flag"))
        await self.channel_layer.group_add(group_name(code), self.channel_name)
        await self.send(text_data=json.dumps({**room.room_msg(), "self": p.id}))

    async def handle_join(self, msg):
        code = str(msg.get("code", "")).upper().strip()
        room = ROOMS.get(code)
        if room is None:
            await self.send(text_data=json.dumps({"t": "err", "msg": "No room with that code"}))
            return
        name = msg.get("name")
        if name and name.lower() in room.banned_names:
            await self.send(text_data=json.dumps({"t": "err", "msg": "You are banned from this room"}))
            return
        if room.started:
            await self.send(text_data=json.dumps({"t": "err", "msg": "Race already started"}))
            return
        if len(room.players) >= room.max:
            await self.send(text_data=json.dumps({"t": "err", "msg": "Room is full"}))
            return
        self.code = code
        p = room.add(self.channel_name, name, msg.get("flag"))
        await self.channel_layer.group_add(group_name(code), self.channel_name)
        await self.send(text_data=json.dumps({**room.room_msg(), "self": p.id}))
        await self.group_broadcast(room.room_msg(), exclude_channel=self.channel_name)
        if room.all_ready() and not room.started:
            await self.start_race(room)

    async def start_race(self, room: Room):
        room.start()
        players = [{"id": p.id, "name": p.name, "flag": p.flag, "slot": p.slot} for p in room.players.values()]
        await self.group_broadcast({"t": "start", "seed": room.seed, "players": players, "settings": room.settings})

    async def group_broadcast(self, data, exclude_channel=None):
        await self.channel_layer.group_send(
            group_name(self.code),
            {"type": "deliver", "data": data, "exclude_channel": exclude_channel},
        )

    # ---- Channels event handlers (dispatched by type) --------------------------------
    async def deliver(self, event):
        if event.get("exclude_channel") == self.channel_name:
            return
        await self.send(text_data=json.dumps(event["data"]))

    async def force_close(self, event):
        await self.close()
