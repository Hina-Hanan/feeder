# game.py  -  Feed the Faces (stick-figure runner version)
import os, sys, math, random, subprocess
import pygame

from netgame import MultiHost, MultiClient, PORT, MAX_PLAYERS, local_ip

pygame.init()
W, H = 1152, 648
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("Feed the Faces")
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 30)
big = pygame.font.SysFont(None, 90)

FOODS = ["apple", "banana", "strawberry", "carrot", "tomato", "eggplant", "avocado", "kiwi"]
COLORS = {"apple": (220, 50, 50), "banana": (245, 220, 60), "strawberry": (230, 40, 70),
          "carrot": (240, 130, 30), "tomato": (235, 90, 70), "eggplant": (130, 70, 170),
          "avocado": (110, 160, 60), "kiwi": (140, 180, 50)}
FOOD_SIZE = 60
TARGET = 5          # fav foods needed to burst
BASE_HEAD = 70      # head size at 0 eaten
GROW = 22           # px added per fav food
MIN_HEAD = 40       # smallest the head can shrink to
RESPAWN_MIN_DIST = 120  # next spawn far from this player's last spot
FOOD_SEP = 100          # keep each player's food away from others
FEET_Y_MIN, FEET_Y_MAX = 280, H - 55   # walk here to eat (feet position)
EAT_FEET_RADIUS = 58
FOOD_RESPAWN_DELAY = 0.35

# ---------- assets ----------
def load_food(name):
    path = f"assets/foods/{name}.png"
    if os.path.exists(path):
        img = pygame.image.load(path).convert_alpha()
        return pygame.transform.smoothscale(img, (FOOD_SIZE, FOOD_SIZE))
    s = pygame.Surface((FOOD_SIZE, FOOD_SIZE), pygame.SRCALPHA)
    c, r = COLORS[name], FOOD_SIZE // 2
    if name == "banana":
        pygame.draw.ellipse(s, c, (0, 14, FOOD_SIZE, 24))
    elif name == "carrot":
        pygame.draw.polygon(s, c, [(4, 8), (48, 8), (26, 50)])
    elif name == "broccoli":
        for x, y in [(14, 16), (26, 10), (38, 16), (26, 24)]:
            pygame.draw.circle(s, c, (x, y), 13)
        pygame.draw.rect(s, c, (20, 28, 12, 22))
    elif name == "grapes":
        for x, y in [(14, 12), (26, 12), (38, 12), (20, 26), (32, 26), (26, 40)]:
            pygame.draw.circle(s, c, (x, y), 9)
    elif name == "tomato":
        pygame.draw.rect(s, c, (4, 8, 44, 38), border_radius=16)
    else:
        pygame.draw.circle(s, c, (r, r), r - 2)
    return s

def circle_crop(img):
    side = min(img.get_size())
    crop = pygame.Rect(0, 0, side, side); crop.center = img.get_rect().center
    img = img.subsurface(crop).copy()
    mask = pygame.Surface((side, side), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (side // 2, side // 2), side // 2)
    img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return img

def load_head(path, crop=True):
    img = pygame.image.load(path).convert_alpha()
    return circle_crop(img) if crop else img

def placeholder_head(color):
    s = pygame.Surface((256, 256), pygame.SRCALPHA)
    pygame.draw.circle(s, color, (128, 128), 128)
    for x in (88, 168):
        pygame.draw.circle(s, (255, 255, 255), (x, 100), 24)
        pygame.draw.circle(s, (20, 20, 20), (x, 100), 10)
    pygame.draw.arc(s, (20, 20, 20), (68, 120, 120, 90), math.pi, 2 * math.pi, 8)
    return s

def pick_file():
    """Open a file picker in a separate process (tkinter crashes inside a pygame window on macOS)."""
    try:
        if sys.platform == "darwin":
            script = 'POSIX path of (choose file of type {"public.image"} with prompt "Choose your face image")'
            out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            return out.stdout.strip() if out.returncode == 0 else ""
        code = ("import tkinter as tk\nfrom tkinter import filedialog\n"
                "r = tk.Tk(); r.withdraw()\n"
                "print(filedialog.askopenfilename(filetypes=[('Images', '*.png *.jpg *.jpeg')]))")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        return out.stdout.strip()
    except Exception:
        return ""

FOOD_IMG = {n: load_food(n) for n in FOODS}
HEAD_CACHE = {}

def load_background():
    path = "assets/background.png"
    if os.path.exists(path):
        img = pygame.image.load(path).convert()
        return pygame.transform.smoothscale(img, (W, H))
    return None

BG = load_background()

def scaled_head(img, key, size):
    k = (key, size)
    if k not in HEAD_CACHE:
        w, h = img.get_size()
        scale = size / max(w, h)
        HEAD_CACHE[k] = pygame.transform.smoothscale(img, (int(w * scale), int(h * scale)))
    return HEAD_CACHE[k]

# ---------- runner (stick figure + head) ----------
class Runner:
    TORSO = 38          # hip to shoulder (shorter body)
    LEG = 34
    ARM = 22

    def __init__(self, name, head, fav, is_player=False, slot=0):
        self.name, self.head, self.fav, self.is_player = name, head, fav, is_player
        self.slot = slot
        self.key = slot
        self.pos = pygame.Vector2(random.randint(100, W - 100), random.randint(250, H - 40))  # feet
        self.count = 0
        self.speed = 280 if is_player else random.randint(110, 160)
        self.facing = 1
        self.run_t = 0.0
        self.moving = False
        self.burst = False
        self.flash = 0.0
        self.meal = None
        self.meal_timer = 0.0
        self.last_meal_pos = None

    @property
    def head_size(self):
        return max(MIN_HEAD, BASE_HEAD + GROW * self.count)

    def head_center(self):
        return pygame.Vector2(self.pos.x, self.pos.y - self.TORSO - self.head_size * 0.52)

    def head_hit_radius(self):
        return self.head_size * 0.5 + 8

    def update_anim(self, dt):
        if self.moving:
            self.run_t += dt * 14
        else:
            self.run_t *= 0.9
        self.flash = max(0, self.flash - dt)
        self.meal_timer = max(0, self.meal_timer - dt)

    def draw(self):
        if self.burst:
            return
        x, y = self.pos.x, self.pos.y
        swing = math.sin(self.run_t) * (0.9 if self.moving else 0)
        hip = pygame.Vector2(x, y - self.TORSO * 0.55)
        shoulder = pygame.Vector2(x, y - self.TORSO)
        ink = (20, 20, 20)
        lw = 5
        # shadow
        pygame.draw.ellipse(screen, (70, 50, 35), (x - 24, y - 5, 48, 12))
        # torso
        pygame.draw.line(screen, ink, hip, shoulder, lw)
        # legs (shorter)
        for s in (1, -1):
            foot = pygame.Vector2(x + s * swing * self.LEG, y - (4 if s * swing > 0 else 0) - max(0, -s * swing) * 6)
            knee = pygame.Vector2((hip.x + foot.x) / 2 + self.facing * 6, (hip.y + foot.y) / 2)
            pygame.draw.lines(screen, ink, False, [hip, knee, foot], lw)
        # arms (shorter)
        for s in (1, -1):
            hand = pygame.Vector2(x + s * self.ARM - s * swing * 12, shoulder.y + 12 + swing * s * 8)
            elbow = pygame.Vector2((shoulder.x + hand.x) / 2, (shoulder.y + hand.y) / 2 + 4)
            pygame.draw.lines(screen, ink, False, [shoulder, elbow, hand], lw)
            pygame.draw.circle(screen, ink, hand, 6)
        # head
        img = scaled_head(self.head, self.key, self.head_size)
        if self.flash > 0:
            img = img.copy()
            img.fill((255, 90, 90, 255), special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(img, img.get_rect(center=self.head_center()))
        # label
        label = font.render(f"{self.name}  {max(0, self.count)}/{TARGET}", True, (20, 20, 20))
        screen.blit(label, label.get_rect(center=(x, y + 22)))

def other_meal_positions(runners, skip=None):
    out = []
    for r in runners:
        if r is skip or r.meal is None:
            continue
        out.append(r.meal["pos"])
    return out

def spawn_runner_meal(runner, runners, avoid_pos=None):
    others = other_meal_positions(runners, skip=runner)
    for _ in range(160):
        pos = pygame.Vector2(random.randint(70, W - 70), random.randint(FEET_Y_MIN, FEET_Y_MAX))
        if avoid_pos is not None and pos.distance_to(avoid_pos) < RESPAWN_MIN_DIST:
            continue
        if any(pos.distance_to(p) < FOOD_SEP for p in others):
            continue
        return {"name": runner.fav, "pos": pos, "owner": runner.slot}
    return {"name": runner.fav, "pos": pos, "owner": runner.slot}

def init_all_meals(runners):
    for r in runners:
        r.meal = None
        r.meal_timer = 0.0
        r.last_meal_pos = None
    for r in runners:
        r.meal = spawn_runner_meal(r, runners)

def ensure_meals(runners):
    for r in runners:
        if r.burst:
            r.meal = None
            continue
        if r.meal is None and r.meal_timer <= 0:
            r.meal = spawn_runner_meal(r, runners, r.last_meal_pos)

def try_eat_meal(runner, meal):
    if meal is None or meal["owner"] != runner.slot:
        return False
    if runner.pos.distance_to(meal["pos"]) > EAT_FEET_RADIUS:
        return False
    runner.count += 1
    return True

def draw_meal(meal, highlight=False):
    center = meal["pos"] + pygame.Vector2(0, -FOOD_SIZE * 0.35)
    screen.blit(FOOD_IMG[meal["name"]], center - pygame.Vector2(FOOD_SIZE / 2, FOOD_SIZE / 2))
    ring = (255, 255, 200) if highlight else (255, 255, 255)
    pygame.draw.ellipse(screen, ring, (meal["pos"].x - 24, meal["pos"].y - 7, 48, 14))
    pygame.draw.ellipse(screen, (60, 45, 30), (meal["pos"].x - 20, meal["pos"].y - 5, 40, 10), 2)

POP_COLORS = [(255, 45, 45), (255, 140, 0), (255, 238, 0), (0, 229, 255),
              (255, 68, 204), (102, 255, 102), (255, 255, 255)]

def spawn_win_burst(g, pos):
    fx = g["fx"]
    x, y = pos.x, pos.y
    for _ in range(55):
        a = random.uniform(0, 2 * math.pi)
        sp = random.uniform(100, 480)
        fx.append({"kind": "fire", "p": pygame.Vector2(x, y),
                   "v": pygame.Vector2(math.cos(a), math.sin(a)) * sp + pygame.Vector2(0, -40),
                   "life": random.uniform(0.35, 0.9), "r": random.uniform(6, 28)})
    for _ in range(80):
        a = random.uniform(0, 2 * math.pi)
        sp = random.uniform(200, 750)
        fx.append({"kind": "spark", "p": pygame.Vector2(x, y),
                   "v": pygame.Vector2(math.cos(a), math.sin(a)) * sp,
                   "life": random.uniform(0.25, 0.7), "r": random.uniform(2, 5)})
    for _ in range(140):
        a = random.uniform(0, 2 * math.pi)
        sp = random.uniform(120, 540)
        fx.append({"kind": "confetti", "p": pygame.Vector2(x, y),
                   "v": pygame.Vector2(math.cos(a), math.sin(a)) * sp + pygame.Vector2(0, -80),
                   "life": random.uniform(1.2, 3.0),
                   "size": (random.randint(6, 14), random.randint(10, 24)),
                   "rot": random.uniform(0, 6.28), "vr": random.uniform(-12, 12),
                   "c": random.choice(POP_COLORS)})
    for _ in range(144):
        a = -math.pi / 2 + random.uniform(-0.6, 0.6)
        sp = random.uniform(280, 600)
        fx.append({"kind": "streamer", "p": pygame.Vector2(x, y),
                   "v": pygame.Vector2(math.cos(a), math.sin(a)) * sp,
                   "life": random.uniform(0.9, 1.7),
                   "c": random.choice(POP_COLORS), "len": random.uniform(12, 32)})

def update_win_fx(g, dt):
    alive = []
    for p in g["fx"]:
        p["life"] -= dt
        if p["life"] <= 0:
            continue
        p["p"] += p["v"] * dt
        k = p["kind"]
        if k == "fire":
            p["v"].y -= 90 * dt
            p["r"] += 28 * dt
            p["v"] *= max(0, 1 - dt * 0.8)
        elif k == "spark":
            p["v"].y += 180 * dt
        elif k == "confetti":
            p["v"].y += 420 * dt
            p["v"] *= max(0, 1 - dt * 0.35)
            p["rot"] += p["vr"] * dt
        elif k == "streamer":
            p["v"].y += 320 * dt
            p["v"] *= max(0, 1 - dt * 0.2)
        alive.append(p)
    g["fx"] = alive
    if g.get("burst_flash", 0) > 0:
        g["burst_flash"] = max(0, g["burst_flash"] - dt)
    if g.get("burst_ring", 0) < 1:
        g["burst_ring"] = min(1, g.get("burst_ring", 0) + dt * 2.2)

def draw_win_fx(g):
    if not g.get("winner"):
        return
    pos = g.get("burst_pos")
    if not pos:
        return
    x, y = pos.x, pos.y
    flash = g.get("burst_flash", 0)
    if flash > 0:
        rad = int(140 + g.get("burst_ring", 0) * 100)
        surf = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (255, 200, 80, int(180 * flash)), (rad, rad), rad)
        pygame.draw.circle(surf, (255, 255, 220, int(120 * flash)), (rad, rad), rad // 2)
        screen.blit(surf, (x - rad, y - rad))
    ring = g.get("burst_ring", 0)
    if ring < 0.85:
        pygame.draw.circle(screen, (255, 200, 50), (int(x), int(y)), int(30 + ring * 110), 8)
    for p in g["fx"]:
        a = max(0, min(1, p["life"] * 2))
        k = p["kind"]
        px, py = int(p["p"].x), int(p["p"].y)
        if k == "fire":
            r = int(p["r"])
            pygame.draw.circle(screen, (255, int(140 + 80 * a), 0), (px, py), max(1, r))
            pygame.draw.circle(screen, (255, 255, 200), (px, py), max(1, r // 2))
        elif k == "spark":
            pygame.draw.circle(screen, (255, 240, 120), (px, py), int(p["r"]))
        elif k == "confetti":
            w, h = p["size"]
            rect = pygame.Surface((w, h), pygame.SRCALPHA)
            rect.fill((*p["c"], int(255 * a)))
            rot = pygame.transform.rotate(rect, math.degrees(p["rot"]))
            screen.blit(rot, rot.get_rect(center=(px, py)))
        elif k == "streamer":
            dx, dy = -p["v"].x * 0.04, -p["v"].y * 0.04 - p["len"]
            pygame.draw.line(screen, p["c"], (px, py), (int(px + dx), int(py + dy)), 4)

def check_win(g, runner):
    if runner.count >= TARGET:
        runner.burst = True
        g["winner"] = runner
        hc = runner.head_center()
        g["burst_pos"] = pygame.Vector2(hc)
        g["burst_flash"] = 0.45
        g["burst_ring"] = 0.0
        spawn_win_burst(g, hc)

MULTI_COLORS = [(250, 200, 150), (240, 170, 120), (160, 200, 240), (200, 240, 160)]

def new_bot_game(player_head, player_fav):
    others = [f for f in FOODS if f != player_fav]
    random.shuffle(others)
    runners = [Runner("You", player_head, player_fav, True, slot=0)]
    for i, n in enumerate(["Mimi", "Bobo", "Zed"]):
        runners.append(Runner(n, placeholder_head(MULTI_COLORS[i + 1]), others[i], slot=i + 1))
    init_all_meals(runners)
    return {"runners": runners, "fx": [], "winner": None, "bubble": None, "use_bots": True,
            "burst_flash": 0, "burst_ring": 0, "burst_pos": None}

def new_multi_game(players, local_slot, local_head):
    runners = []
    for p in sorted(players, key=lambda x: x["slot"]):
        is_local = p["slot"] == local_slot
        head = local_head if is_local else placeholder_head(MULTI_COLORS[p["slot"] % len(MULTI_COLORS)])
        runners.append(Runner(p["name"], head, p["fav"], is_local, slot=p["slot"]))
    init_all_meals(runners)
    return {"runners": runners, "fx": [], "winner": None, "bubble": None, "use_bots": False,
            "burst_flash": 0, "burst_ring": 0, "burst_pos": None}

def read_move(keys):
    return (keys[pygame.K_d] - keys[pygame.K_a] + keys[pygame.K_RIGHT] - keys[pygame.K_LEFT],
            keys[pygame.K_s] - keys[pygame.K_w] + keys[pygame.K_DOWN] - keys[pygame.K_UP])

def apply_move(runner, mx, my, dt):
    move = pygame.Vector2(mx, my)
    runner.moving = move.length() > 0
    if runner.moving:
        move = move.normalize()
        runner.pos += move * runner.speed * dt
        if move.x:
            runner.facing = 1 if move.x > 0 else -1

def sim_step(g, dt, inputs_by_slot):
    runners = g["runners"]
    if g["winner"] is not None:
        return
    ensure_meals(runners)
    use_bots = g.get("use_bots", False)
    for r in runners:
        if use_bots and not r.is_player:
            if r.meal:
                d = r.meal["pos"] - r.pos
                r.moving = d.length() > EAT_FEET_RADIUS
                if r.moving and d.length() > 1:
                    r.pos += d.normalize() * r.speed * dt
                    if d.x:
                        r.facing = 1 if d.x > 0 else -1
            else:
                r.moving = False
        elif r.slot in inputs_by_slot:
            apply_move(r, *inputs_by_slot[r.slot], dt)
    for r in runners:
        r.pos.x = max(30, min(W - 30, r.pos.x))
        r.pos.y = max(FEET_Y_MIN - 20, min(H - 30, r.pos.y))
        r.update_anim(dt)
    for r in runners:
        if r.meal and try_eat_meal(r, r.meal):
            r.last_meal_pos = r.meal["pos"].copy()
            r.meal = None
            r.meal_timer = FOOD_RESPAWN_DELAY
            check_win(g, r)

def pack_game_state(g):
    def pack_meal(m):
        if m is None:
            return None
        return {"name": m["name"], "pos": [m["pos"].x, m["pos"].y], "owner": m["owner"]}
    return {
        "runners": [{
            "slot": r.slot, "name": r.name, "fav": r.fav,
            "pos": [r.pos.x, r.pos.y], "count": r.count, "facing": r.facing,
            "moving": r.moving, "burst": r.burst, "flash": r.flash,
            "meal": pack_meal(r.meal), "meal_timer": r.meal_timer,
        } for r in g["runners"]],
        "winner_slot": g["winner"].slot if g.get("winner") else None,
    }

def apply_game_state(g, state):
    if not state:
        return
    by_slot = {r.slot: r for r in g["runners"]}
    for rd in state.get("runners", []):
        r = by_slot.get(rd["slot"])
        if not r:
            continue
        r.name = rd["name"]
        r.fav = rd["fav"]
        r.pos.update(rd["pos"])
        r.count = rd["count"]
        r.facing = rd["facing"]
        r.moving = rd["moving"]
        r.burst = rd["burst"]
        r.flash = rd["flash"]
        r.meal_timer = rd.get("meal_timer", 0)
        m = rd.get("meal")
        if m:
            r.meal = {"name": m["name"], "pos": pygame.Vector2(m["pos"]), "owner": m["owner"]}
        else:
            r.meal = None
    ws = state.get("winner_slot")
    if ws is not None:
        g["winner"] = by_slot.get(ws)
    else:
        g["winner"] = None

def close_net():
    global net  # noqa: PLW0603
    if net:
        net.close()
        net = None

def draw_button(rect, label, selected=False):
    pygame.draw.rect(screen, (255, 255, 255) if selected else (230, 230, 230), rect, border_radius=14)
    pygame.draw.rect(screen, (40, 40, 40), rect, 2, border_radius=14)
    t = font.render(label, True, (20, 20, 20))
    screen.blit(t, t.get_rect(center=rect.center))

# ---------- main ----------
state = "mode_select"
play_mode = "bots"  # bots | multi
is_host = False
net = None
local_slot = 0
join_ip = "127.0.0.1"
player_name = "You"
default_path = "assets/faces/head.png"
player_head = load_head(default_path, crop=False) if os.path.exists(default_path) else placeholder_head((250, 200, 150))
fav_choice = 0
g = None
status_msg = ""

def menu_food_rect(i):
    return pygame.Rect(40 + i * 135, 360, 110, 110)

MODE_BOT = pygame.Rect(W // 2 - 220, 280, 440, 56)
MODE_MULTI = pygame.Rect(W // 2 - 220, 360, 440, 56)
MULTI_HOST = pygame.Rect(W // 2 - 220, 300, 440, 56)
MULTI_JOIN = pygame.Rect(W // 2 - 220, 380, 440, 56)
MENU_CONTINUE = pygame.Rect(W // 2 - 180, 500, 360, 52)

def continue_from_menu():
    global g, net, state, local_slot, status_msg
    HEAD_CACHE.clear()
    fav = FOODS[fav_choice]
    if play_mode == "multi" and is_host:
        try:
            close_net()
            net = MultiHost(player_name, fav)
            state = "lobby"
            status_msg = ""
        except OSError:
            status_msg = f"Cannot host: port {PORT} in use. Quit other game windows and try again."
    elif play_mode == "multi":
        try:
            close_net()
            net = MultiClient(join_ip.strip() or "127.0.0.1")
            net.send_join(player_name, fav)
            state = "wait_lobby"
            status_msg = ""
        except OSError:
            net = None
            status_msg = f"Cannot connect to {join_ip}. Check IP and that host is in the lobby."
    else:
        g = new_bot_game(player_head, fav)
        state = "play"
        status_msg = ""

running = True
while running:
    dt = clock.tick(60) / 1000
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False
        elif state == "mode_select":
            if e.type == pygame.KEYDOWN and e.key == pygame.K_1:
                play_mode = "bots"
                is_host = False
                state = "menu"
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_2:
                play_mode = "multi"
                state = "multi_pick"
            elif e.type == pygame.MOUSEBUTTONDOWN:
                if MODE_BOT.collidepoint(e.pos):
                    play_mode = "bots"
                    is_host = False
                    state = "menu"
                elif MODE_MULTI.collidepoint(e.pos):
                    play_mode = "multi"
                    state = "multi_pick"
        elif state == "multi_pick":
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                state = "mode_select"
            elif e.type == pygame.KEYDOWN and e.key in (pygame.K_h, pygame.K_RETURN, pygame.K_SPACE):
                play_mode = "multi"
                is_host = True
                state = "menu"
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_j:
                play_mode = "multi"
                is_host = False
                state = "join_ip"
            elif e.type == pygame.MOUSEBUTTONDOWN:
                if MULTI_HOST.collidepoint(e.pos):
                    play_mode = "multi"
                    is_host = True
                    state = "menu"
                elif MULTI_JOIN.collidepoint(e.pos):
                    play_mode = "multi"
                    is_host = False
                    state = "join_ip"
        elif state == "join_ip":
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                state = "multi_pick"
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_BACKSPACE:
                join_ip = join_ip[:-1]
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
                state = "menu"
            elif e.type == pygame.KEYDOWN and len(e.unicode) == 1 and e.unicode.isprintable():
                if len(join_ip) < 40:
                    join_ip += e.unicode
        elif state == "menu":
            if e.type == pygame.KEYDOWN and e.key == pygame.K_u:
                p = pick_file()
                if p:
                    player_head = load_head(p, crop=True)
            elif e.type == pygame.MOUSEBUTTONDOWN:
                for i in range(len(FOODS)):
                    if menu_food_rect(i).collidepoint(e.pos):
                        fav_choice = i
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                close_net()
                state = "mode_select" if play_mode == "bots" else "multi_pick"
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
                continue_from_menu()
            elif e.type == pygame.MOUSEBUTTONDOWN and MENU_CONTINUE.collidepoint(e.pos):
                continue_from_menu()
        elif state == "lobby":
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                close_net()
                state = "menu"
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
                if net and len(net.players) >= 1:
                    net.start_game()
                    local_slot = 0
                    g = new_multi_game(net.players, local_slot, player_head)
                    state = "play"
        elif state == "wait_lobby":
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                close_net()
                state = "join_ip"
        elif state == "play":
            if e.type == pygame.MOUSEBUTTONDOWN and g and g["winner"] is None and g.get("use_bots"):
                for r in g["runners"][1:]:
                    if r.head_center().distance_to(e.pos) < r.head_size / 2 + 10:
                        g["bubble"] = (r, 2.5)
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_r:
                close_net()
                state = "mode_select"

    if BG:
        screen.blit(BG, (0, 0))
    else:
        screen.fill((200, 230, 190))

    if state == "mode_select":
        screen.blit(big.render("Feed the Faces", True, (40, 60, 40)), (330, 50))
        screen.blit(font.render("Choose how you want to play", True, (30, 30, 30)), (430, 200))
        draw_button(MODE_BOT, "1 — Play with Bots")
        draw_button(MODE_MULTI, "2 — Multiplayer (LAN)")
    elif state == "multi_pick":
        screen.blit(big.render("Multiplayer", True, (40, 60, 40)), (400, 80))
        screen.blit(font.render("Host a game or join a friend on the same Wi‑Fi", True, (30, 30, 30)), (310, 200))
        draw_button(MULTI_HOST, "H / SPACE — Host game")
        draw_button(MULTI_JOIN, "J — Join game")
        screen.blit(font.render("ESC = back", True, (30, 30, 30)), (500, 480))
    elif state == "join_ip":
        screen.blit(big.render("Join", True, (40, 60, 40)), (500, 120))
        screen.blit(font.render("Type host IP address, then ENTER", True, (30, 30, 30)), (380, 220))
        pygame.draw.rect(screen, (255, 255, 255), (300, 300, 550, 50), border_radius=10)
        screen.blit(font.render(join_ip + "|", True, (20, 20, 20)), (320, 315))
        screen.blit(font.render("Next: pick face & food, then SPACE to connect", True, (30, 30, 30)), (290, 400))
    elif state == "lobby":
        if net:
            net.poll()
        screen.blit(big.render("Lobby", True, (40, 60, 40)), (480, 60))
        ip, port = net.address if net else (local_ip(), PORT)
        screen.blit(font.render(f"Your IP: {ip}   Port: {port}", True, (20, 20, 20)), (360, 150))
        screen.blit(font.render("Friends join with J → enter this IP", True, (30, 30, 30)), (350, 190))
        n = len(net.players) if net else 0
        screen.blit(font.render(f"Players ({n}/{MAX_PLAYERS}):", True, (20, 20, 20)), (360, 250))
        y = 290
        if net:
            for p in net.players:
                line = f"  {p['name']} — loves {p['fav']}"
                screen.blit(font.render(line, True, (30, 30, 30)), (380, y))
                y += 36
        hint = "SPACE to start" if n >= 2 else "SPACE to start alone (or wait for friends to join)"
        screen.blit(font.render(hint, True, (30, 30, 30)), (300, 500))
    elif state == "wait_lobby":
        if net:
            net.poll()
            if net.slot is not None:
                local_slot = net.slot
            if net.started and net.slot is not None:
                g = new_multi_game(net.players, local_slot, player_head)
                state = "play"
        screen.blit(big.render("Waiting…", True, (40, 60, 40)), (420, 120))
        screen.blit(font.render("Connected! Waiting for host to start…", True, (30, 30, 30)), (330, 240))
        if net:
            for i, p in enumerate(net.players):
                screen.blit(font.render(f"{p['name']} ({p['fav']})", True, (30, 30, 30)), (400, 300 + i * 34))
        screen.blit(font.render("ESC = disconnect", True, (30, 30, 30)), (470, 500))
    elif state == "menu":
        title = "Setup — Bots" if play_mode == "bots" else ("Setup — Host" if is_host else "Setup — Join")
        screen.blit(big.render("Feed the Faces", True, (40, 60, 40)), (330, 50))
        screen.blit(font.render(title, True, (30, 30, 30)), (460, 130))
        if is_host and play_mode == "multi":
            screen.blit(font.render("Pick your face & favorite food, then open the lobby",
                                    True, (30, 30, 30)), (300, 170))
        else:
            screen.blit(font.render("U = upload face   |   click favorite food",
                                    True, (30, 30, 30)), (350, 170))
        screen.blit(font.render("Everyone has their own favorite — first to 5 wins!",
                                True, (30, 30, 30)), (280, 210))
        screen.blit(scaled_head(player_head, "menu", 150), (40, 330))
        for i, n in enumerate(FOODS):
            r = menu_food_rect(i)
            if i == fav_choice:
                pygame.draw.rect(screen, (255, 255, 255), r, border_radius=12)
            screen.blit(pygame.transform.smoothscale(FOOD_IMG[n], (90, 90)), (r.x + 10, r.y + 10))
        cont = "Open Lobby" if (play_mode == "multi" and is_host) else ("Connect" if play_mode == "multi" else "Start Game")
        draw_button(MENU_CONTINUE, f"SPACE — {cont}")
        if status_msg:
            screen.blit(font.render(status_msg, True, (180, 30, 30)), (200, 560))

    elif state == "play" and g:
        runners = g["runners"]
        me = next((r for r in runners if r.is_player), runners[0])
        keys = pygame.key.get_pressed()
        mx, my = read_move(keys)

        if play_mode == "multi" and net:
            net.poll()
            if isinstance(net, MultiHost):
                net.set_host_input(mx, my)
                inputs = net.get_inputs()
                sim_step(g, dt, inputs)
                net.broadcast_state(pack_game_state(g))
            else:
                net.send_input(mx, my)
                apply_game_state(g, net.latest_state)
        else:
            sim_step(g, dt, {me.slot: (mx, my)})

        # meals under characters (feet sort)
        for r in runners:
            if r.meal:
                draw_meal(r.meal, highlight=r.is_player)
        if me.meal and me.meal["pos"].distance_to(me.pos) > 70:
            dirv = me.meal["pos"] - me.pos
            if dirv.length() > 1:
                dirv.scale_to_length(36)
                ax, ay = me.pos.x + dirv.x, me.pos.y + dirv.y - 50
                ang = math.atan2(dirv.y, dirv.x)
                tri = [
                    (ax + math.cos(ang) * 10, ay + math.sin(ang) * 10),
                    (ax + math.cos(ang + 2.5) * 8, ay + math.sin(ang + 2.5) * 8),
                    (ax + math.cos(ang - 2.5) * 8, ay + math.sin(ang - 2.5) * 8),
                ]
                pygame.draw.polygon(screen, (255, 230, 80), tri)
        for r in sorted(runners, key=lambda r: r.pos.y):
            r.draw()

        # HUD: your favorite
        pygame.draw.rect(screen, (255, 255, 255), (10, 10, 230, 60), border_radius=12)
        screen.blit(font.render("Your food:", True, (20, 20, 20)), (22, 30))
        screen.blit(pygame.transform.smoothscale(FOOD_IMG[me.fav], (44, 44)), (150, 18))

        if g["bubble"]:
            r, t = g["bubble"]
            t -= dt
            g["bubble"] = (r, t) if t > 0 else None
            bc = r.head_center()
            bx, by = bc.x - 80, bc.y - r.head_size / 2 - 66
            pygame.draw.rect(screen, (255, 255, 255), (bx, by, 160, 56), border_radius=14)
            screen.blit(font.render("I love", True, (20, 20, 20)), (bx + 14, by + 18))
            screen.blit(pygame.transform.smoothscale(FOOD_IMG[r.fav], (40, 40)), (bx + 100, by + 8))

        if g["winner"]:
            update_win_fx(g, dt)
            draw_win_fx(g)
            overlay = pygame.Surface((W, H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 90))
            screen.blit(overlay, (0, 0))
            w = g["winner"]
            msg = big.render(f"{w.name} wins!", True, (255, 221, 85))
            outline = big.render(f"{w.name} wins!", True, (139, 32, 32))
            r = msg.get_rect(center=(W // 2, H // 2))
            screen.blit(outline, r.move(2, 2))
            screen.blit(msg, r)
            screen.blit(font.render("Press R for main menu", True, (20, 20, 20)), (W // 2 - 95, H // 2 + 60))

    pygame.display.flip()

pygame.quit()