"""Client-side networking for Steer multiplayer.

Runs a websockets asyncio loop on a daemon thread so the pygame main loop never
blocks. The game talks to it with plain dicts: send() to push a message, poll() to
drain everything that has arrived since the last frame.

Server URL comes from the STEER_SERVER_URL env var, else the default below — point it
at your Render deployment (wss://your-app.onrender.com).
"""
import asyncio
import json
import os
import queue
import threading
import time
import urllib.request
from urllib.parse import urlparse

import websockets

DEFAULT_URL = os.environ.get("STEER_SERVER_URL", "ws://localhost:8765")


def prewarm(url=None):
    # Render's free plan spins a server down after idle and takes ~30s to cold-start on the
    # next request. Fire a one-shot HTTP ping at game launch (not when the player clicks
    # Host/Join) so that wait mostly happens in the background while they're in the menus.
    target = url or DEFAULT_URL
    if urlparse(target).hostname in ("localhost", "127.0.0.1", None):
        return
    http_url = target.replace("wss://", "https://").replace("ws://", "http://")

    def _ping():
        try:
            urllib.request.urlopen(http_url, timeout=35)
        except Exception:
            pass
    threading.Thread(target=_ping, daemon=True).start()


class Net:
    def __init__(self, url=None):
        self.url = url or DEFAULT_URL
        self.status = "idle"        # idle | connecting | connected | error | closed
        self.error = None
        self._in = queue.Queue()    # messages from server -> game (thread-safe)
        self._loop = None
        self._ws = None
        self._out = None            # asyncio.Queue, created inside the loop
        self._thread = None
        self._connect_t = 0.0

    # ---- public, called from the game thread ------------------------------------
    def connect(self):
        self.status = "connecting"
        self._connect_t = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def waking(self):
        # Render's free plan can take up to a minute to wake from idle; tell the UI if the
        # connection is taking a while so it can say so
        return self.status == "connecting" and (time.monotonic() - self._connect_t) > 5.0

    def connect_elapsed(self):
        return time.monotonic() - self._connect_t if self._connect_t else 0.0

    def send(self, obj):
        loop, out = self._loop, self._out
        if loop is not None and out is not None:
            loop.call_soon_threadsafe(out.put_nowait, obj)

    def poll(self):
        msgs = []
        while True:
            try:
                msgs.append(self._in.get_nowait())
            except queue.Empty:
                break
        return msgs

    def close(self):
        loop, out = self._loop, self._out
        if loop is not None and out is not None:
            loop.call_soon_threadsafe(out.put_nowait, None)

    # ---- background thread ------------------------------------------------------
    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._session())
        except Exception as e:
            self.status, self.error = "error", str(e)
            self._in.put({"t": "neterr", "msg": str(e)})
        finally:
            if self.status not in ("error",):
                self.status = "closed"

    async def _session(self):
        self._out = asyncio.Queue()
        async with websockets.connect(self.url, ping_interval=20, open_timeout=60) as ws:
            self._ws = ws
            self.status = "connected"
            self._in.put({"t": "netopen"})
            sender = asyncio.ensure_future(self._sender(ws))
            try:
                async for raw in ws:
                    try:
                        self._in.put(json.loads(raw))
                    except (ValueError, TypeError):
                        pass
            finally:
                sender.cancel()

    async def _sender(self, ws):
        while True:
            obj = await self._out.get()
            if obj is None:
                await ws.close()
                return
            await ws.send(json.dumps(obj))
