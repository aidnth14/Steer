import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import unittest

import websockets

import net

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestNetClient(unittest.TestCase):
    def test_close_before_connect_is_safe(self):
        n = net.Net("ws://127.0.0.1:1")     # never connected
        n.close()                           # must not raise
        self.assertEqual(n.poll(), [])


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


async def recv_until(ws, kind, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        raw = await asyncio.wait_for(ws.recv(), timeout=end - time.time())
        msg = json.loads(raw)
        if msg.get("t") == kind:
            return msg
    raise AssertionError(f"timed out waiting for {kind!r}")


async def drain(ws, seconds=0.8):
    out = []
    end = time.time() + seconds
    while time.time() < end:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=end - time.time())
            out.append(json.loads(raw))
        except (asyncio.TimeoutError, websockets.ConnectionClosed):
            break
    return out


class TestNet(unittest.TestCase):
    def setUp(self):
        self.port = free_port()
        env = dict(os.environ, PORT=str(self.port))
        self.proc = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # wait for the port to accept connections
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

    def tearDown(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def url(self):
        return f"ws://127.0.0.1:{self.port}"

    def run_async(self, coro):
        return asyncio.run(asyncio.wait_for(coro, timeout=15))

    def test_host_join_ready_start(self):
        async def scenario():
            async with websockets.connect(self.url()) as host, \
                    websockets.connect(self.url()) as joiner:
                host.send  # noqa
                await host.send(json.dumps({"t": "host", "name": "H", "flag": "bd", "max": 4}))
                room = await recv_until(host, "room")
                code = room["code"]
                await joiner.send(json.dumps({"t": "join", "code": code, "name": "J", "flag": "us"}))
                await recv_until(joiner, "room")
                await host.send(json.dumps({"t": "ready", "v": True}))
                await joiner.send(json.dumps({"t": "ready", "v": True}))
                hstart = await recv_until(host, "start")
                jstart = await recv_until(joiner, "start")
                self.assertEqual(hstart["seed"], jstart["seed"])
        self.run_async(scenario())

    def test_kick(self):
        async def scenario():
            async with websockets.connect(self.url()) as host, \
                    websockets.connect(self.url()) as joiner:
                await host.send(json.dumps({"t": "host", "name": "H", "flag": "bd", "max": 4}))
                hroom = await recv_until(host, "room")
                await joiner.send(json.dumps({"t": "join", "code": hroom["code"], "name": "J"}))
                jroom = await recv_until(joiner, "room")
                jid = jroom["self"]
                await host.send(json.dumps({"t": "kick", "id": jid}))
                kicked = await recv_until(joiner, "kicked")
                self.assertEqual(kicked["t"], "kicked")
        self.run_async(scenario())

    def test_host_migration(self):
        async def scenario():
            host = await websockets.connect(self.url())
            joiner = await websockets.connect(self.url())
            try:
                await host.send(json.dumps({"t": "host", "name": "H"}))
                hroom = await recv_until(host, "room")
                await joiner.send(json.dumps({"t": "join", "code": hroom["code"], "name": "J"}))
                jroom = await recv_until(joiner, "room")
                jid = jroom["self"]
                await host.close()                      # host leaves
                # joiner should see a room where it is now the host
                promoted = None
                for _ in range(10):
                    m = await recv_until(joiner, "room", timeout=5)
                    if m.get("host") == jid:
                        promoted = m
                        break
                self.assertIsNotNone(promoted, "joiner was not promoted to host")
            finally:
                await joiner.close()
        self.run_async(scenario())

    def test_nonhost_cannot_send_authoritative(self):
        async def scenario():
            async with websockets.connect(self.url()) as host, \
                    websockets.connect(self.url()) as joiner:
                await host.send(json.dumps({"t": "host", "name": "H", "max": 4}))
                hroom = await recv_until(host, "room")
                await joiner.send(json.dumps({"t": "join", "code": hroom["code"], "name": "J"}))
                await recv_until(joiner, "room")
                await recv_until(host, "room")          # host sees joiner arrive
                # a non-host 'finished' must NOT be relayed to the host
                await joiner.send(json.dumps({"t": "finished", "order": [0, 1]}))
                msgs = await drain(host, 1.0)
                self.assertFalse(any(m.get("t") == "finished" for m in msgs),
                                 "server relayed a non-host authoritative message")
        self.run_async(scenario())


if __name__ == "__main__":
    unittest.main()
