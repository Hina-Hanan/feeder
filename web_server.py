"""Browser multiplayer server (WebSocket). Serves static files from public/ if present."""
import asyncio
import json
import math
import os
import random
import string
from pathlib import Path

from aiohttp import web

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "public" if (ROOT / "public" / "index.html").is_file() else ROOT / "web"

W, H = 1152, 648
FOODS = ["apple", "banana", "strawberry", "carrot", "tomato", "eggplant", "avocado", "kiwi"]
TARGET = 5
BASE_HEAD = 70
GROW = 22
MIN_HEAD = 40
TORSO = 38
SPEED = 280
RESPAWN_MIN_DIST = 120
FOOD_SEP = 100
FEET_Y_MIN, FEET_Y_MAX = 280, H - 55
EAT_FEET_RADIUS = 58
FOOD_RESPAWN_DELAY = 0.35
MAX_PLAYERS = 4
PLAYER_COLORS = ["#f0c896", "#f0aa78", "#a0c8f0", "#c8f0a0"]

rooms: dict[str, "GameRoom"] = {}


def new_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=5))


def dist(ax, ay, bx, by) -> float:
    return math.hypot(ax - bx, ay - by)


class GameRoom:
    def __init__(self, code: str):
        self.code = code
        self.host_ws = None
        self.clients: dict[web.WebSocketResponse, dict] = {}
        self.started = False
        self.winner_slot = None
        self.players: list[dict] = []
        self.inputs: dict[int, tuple[int, int]] = {}
        self.tick_task: asyncio.Task | None = None

    def player_list(self):
        return [{"slot": p["slot"], "name": p["name"], "fav": p["fav"]} for p in self.players]

    def add_player(self, ws, name: str, fav: str, face: str | None = None) -> dict | None:
        if self.started or len(self.players) >= MAX_PLAYERS:
            return None
        if fav not in FOODS:
            fav = random.choice(FOODS)
        if face and len(face) > 600_000:
            face = None
        slot = len(self.players)
        p = {
            "slot": slot,
            "name": name[:16] or f"Player{slot + 1}",
            "fav": fav,
            "face": face,
            "x": random.randint(100, W - 100),
            "y": random.randint(250, H - 40),
            "count": 0,
            "facing": 1,
            "moving": False,
            "burst": False,
            "flash": 0.0,
            "meal": None,
            "meal_timer": 0.0,
            "last_meal_pos": None,
            "run_t": 0.0,
            "color": PLAYER_COLORS[slot % len(PLAYER_COLORS)],
        }
        p["ws"] = ws
        self.players.append(p)
        self.clients[ws] = p
        self.inputs[slot] = (0, 0)
        if slot == 0:
            self.host_ws = ws
        return p

    def remove_player(self, ws):
        self.clients.pop(ws, None)
        if ws == self.host_ws:
            self.host_ws = next(iter(self.clients), None)

    def other_meal_positions(self, skip_slot):
        out = []
        for p in self.players:
            if p["slot"] == skip_slot or not p["meal"]:
                continue
            out.append(p["meal"]["pos"])
        return out

    def spawn_meal(self, player, avoid=None):
        others = self.other_meal_positions(player["slot"])
        for _ in range(160):
            x = random.randint(70, W - 70)
            y = random.randint(FEET_Y_MIN, FEET_Y_MAX)
            if avoid and dist(x, y, avoid[0], avoid[1]) < RESPAWN_MIN_DIST:
                continue
            if any(dist(x, y, ox, oy) < FOOD_SEP for ox, oy in others):
                continue
            return {"name": player["fav"], "pos": [x, y], "owner": player["slot"]}
        return {"name": player["fav"], "pos": [x, y], "owner": player["slot"]}

    def init_meals(self):
        for p in self.players:
            p["meal"] = None
            p["meal_timer"] = 0.0
            p["last_meal_pos"] = None
        for p in self.players:
            p["meal"] = self.spawn_meal(p)

    def ensure_meals(self):
        for p in self.players:
            if p["burst"]:
                p["meal"] = None
                continue
            if p["meal"] is None and p["meal_timer"] <= 0:
                avoid = p["last_meal_pos"]
                p["meal"] = self.spawn_meal(p, avoid)

    def head_size(self, p):
        return max(MIN_HEAD, BASE_HEAD + GROW * p["count"])

    def try_eat(self, p):
        m = p["meal"]
        if not m or m["owner"] != p["slot"]:
            return False
        mx, my = m["pos"]
        if dist(p["x"], p["y"], mx, my) > EAT_FEET_RADIUS:
            return False
        p["count"] += 1
        p["last_meal_pos"] = [mx, my]
        p["meal"] = None
        p["meal_timer"] = FOOD_RESPAWN_DELAY
        if p["count"] >= TARGET:
            p["burst"] = True
            self.winner_slot = p["slot"]
        return True

    def step(self, dt: float):
        if self.winner_slot is not None:
            return
        self.ensure_meals()
        for p in self.players:
            if p["burst"]:
                continue
            mx, my = self.inputs.get(p["slot"], (0, 0))
            move_len = math.hypot(mx, my)
            p["moving"] = move_len > 0
            if move_len > 0:
                nx, ny = mx / move_len, my / move_len
                p["x"] += nx * SPEED * dt
                p["y"] += ny * SPEED * dt
                if mx:
                    p["facing"] = 1 if mx > 0 else -1
            p["x"] = max(30, min(W - 30, p["x"]))
            p["y"] = max(FEET_Y_MIN - 20, min(H - 30, p["y"]))
            if p["moving"]:
                p["run_t"] += dt * 14
            else:
                p["run_t"] *= 0.9
            p["flash"] = max(0, p["flash"] - dt)
            p["meal_timer"] = max(0, p["meal_timer"] - dt)
        for p in self.players:
            self.try_eat(p)

    def public_state(self):
        return {
            "started": self.started,
            "players": self.player_list(),
            "winner_slot": self.winner_slot,
            "runners": [{
                "slot": p["slot"],
                "name": p["name"],
                "fav": p["fav"],
                "x": p["x"],
                "y": p["y"],
                "count": p["count"],
                "facing": p["facing"],
                "moving": p["moving"],
                "burst": p["burst"],
                "flash": p["flash"],
                "run_t": p["run_t"],
                "head_size": self.head_size(p),
                "color": p["color"],
                "meal": p["meal"],
                "face": p.get("face"),
            } for p in self.players],
        }

    async def broadcast(self, msg: dict):
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(msg)
            except ConnectionResetError:
                dead.append(ws)
        for ws in dead:
            self.remove_player(ws)

    async def tick_loop(self):
        try:
            while self.code in rooms and self.started:
                self.step(1 / 30)
                await self.broadcast({"type": "state", "state": self.public_state()})
                await asyncio.sleep(1 / 30)
        except asyncio.CancelledError:
            pass

    def start_match(self):
        if self.started or not self.players:
            return False
        self.started = True
        self.winner_slot = None
        for p in self.players:
            p["count"] = 0
            p["burst"] = False
            p["x"] = random.randint(100, W - 100)
            p["y"] = random.randint(250, H - 40)
        self.init_meals()
        return True


async def ws_handler(request: web.Request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    room_code = request.query.get("room", "").upper().strip()
    if not room_code:
        await ws.send_json({"type": "error", "message": "Missing room code."})
        await ws.close()
        return ws
    room = rooms.get(room_code)
    if not room:
        rooms[room_code] = GameRoom(room_code)
        room = rooms[room_code]

    player = None
    try:
        async for msg in ws:
            if msg.type != web.WSMsgType.TEXT:
                continue
            data = json.loads(msg.data)
            t = data.get("type")
            if t == "join":
                player = room.add_player(
                    ws,
                    data.get("name", "Player"),
                    data.get("fav", "apple"),
                    data.get("face"),
                )
                if not player:
                    await ws.send_json({"type": "error", "message": "Room full or game already started."})
                    await ws.close()
                    break
                await ws.send_json({
                    "type": "joined",
                    "slot": player["slot"],
                    "is_host": player["slot"] == 0,
                    "room": room.code,
                    "players": room.player_list(),
                    "foods": FOODS,
                })
                await room.broadcast({"type": "lobby", "players": room.player_list()})
            elif t == "input" and player:
                room.inputs[player["slot"]] = (
                    int(data.get("mx", 0)),
                    int(data.get("my", 0)),
                )
            elif t == "start" and player and player["slot"] == 0:
                if room.start_match():
                    if room.tick_task:
                        room.tick_task.cancel()
                    room.tick_task = asyncio.create_task(room.tick_loop())
                    await room.broadcast({"type": "start", "state": room.public_state()})
    finally:
        if player and not room.started:
            room.players = [p for p in room.players if p.get("ws") is not ws]
            room.inputs = {p["slot"]: (0, 0) for p in room.players}
        room.remove_player(ws)
        if room.clients:
            await room.broadcast({"type": "lobby", "players": room.player_list()})
        if not room.clients:
            if room.tick_task:
                room.tick_task.cancel()
            rooms.pop(room.code, None)
    return ws


async def create_room(_request: web.Request):
    code = new_code()
    while code in rooms:
        code = new_code()
    rooms[code] = GameRoom(code)
    return web.json_response({"room": code, "url_path": f"/?room={code}"})


async def index(_request: web.Request):
    return web.FileResponse(WEB / "index.html")


async def health(_request: web.Request):
    return web.json_response({"ok": True, "rooms": len(rooms)})


def main():
    app = web.Application()
    app.router.add_post("/api/create-room", create_room)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/health", health)
    app.router.add_get("/", index)
    def static_file(file_path: Path):
        async def handler(_request: web.Request):
            return web.FileResponse(file_path)

        return handler

    for name in ("game.js", "sim.js", "style.css", "winfx.js", "ws-config.js", "embedded-config.js"):
        p = WEB / name
        if p.is_file():
            app.router.add_get(f"/{name}", static_file(p))
    assets = WEB / "assets"
    if not assets.is_dir():
        assets = ROOT / "assets"
    if assets.is_dir():
        app.router.add_static("/assets/", assets)
    port = int(os.environ.get("PORT", "8080"))
    print("Feed the Faces — browser edition")
    print(f"Open:  http://localhost:{port}")
    print("Share: ?room=CODE  (Create game on home page, then Join room)")
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
