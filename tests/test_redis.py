import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import unittest

try:
    import websockets
    import redis  # noqa: F401
    HAVE_LIBS = True
except ImportError:
    HAVE_LIBS = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REDIS_BIN = shutil.which("redis-server")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_port(port, timeout=6):
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


async def recv_until(ws, kind, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=end - time.time()))
        if m.get("t") == kind:
            return m
    raise AssertionError(f"timeout waiting for {kind}")


@unittest.skipUnless(HAVE_LIBS and REDIS_BIN, "redis-server / redis / websockets not available")
class TestRedisCluster(unittest.TestCase):
    def setUp(self):
        self.rport = free_port()
        self.redis = subprocess.Popen(
            [REDIS_BIN, "--port", str(self.rport), "--save", "", "--appendonly", "no"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertTrue(wait_port(self.rport), "redis did not start")
        url = f"redis://127.0.0.1:{self.rport}"
        self.pa, self.pb = free_port(), free_port()
        env = dict(os.environ, REDIS_URL=url)
        self.sa = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT,
                                   env=dict(env, PORT=str(self.pa)),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.sb = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT,
                                   env=dict(env, PORT=str(self.pb)),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertTrue(wait_port(self.pa) and wait_port(self.pb), "servers did not start")
        time.sleep(0.8)     # let the Redis subscribers come up

    def tearDown(self):
        for p in (self.sa, self.sb, self.redis):
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()

    def test_cross_instance_lobby(self):
        async def scenario():
            host = await websockets.connect(f"ws://127.0.0.1:{self.pa}")
            joiner = await websockets.connect(f"ws://127.0.0.1:{self.pb}")
            try:
                await host.send(json.dumps({"t": "host", "name": "A", "flag": "bd", "max": 4}))
                room = await recv_until(host, "room")
                code = room["code"]
                # join a lobby hosted on a *different* instance
                await joiner.send(json.dumps({"t": "join", "code": code, "name": "B"}))
                jroom = await recv_until(joiner, "room")
                self.assertIn("self", jroom)
                self.assertEqual(len(jroom["players"]), 2)
                # both ready -> both receive the same start seed across instances
                await host.send(json.dumps({"t": "ready", "v": True}))
                await joiner.send(json.dumps({"t": "ready", "v": True}))
                hs = await recv_until(host, "start")
                js = await recv_until(joiner, "start")
                self.assertEqual(hs["seed"], js["seed"])
                # host's authoritative state relays cross-instance to the joiner
                await host.send(json.dumps({"t": "state", "slot": 0, "car": {"x": 1.0}}))
                st = await recv_until(joiner, "state")
                self.assertEqual(st["car"]["x"], 1.0)
            finally:
                await host.close()
                await joiner.close()
        asyncio.run(asyncio.wait_for(scenario(), timeout=15))


if __name__ == "__main__":
    unittest.main()
