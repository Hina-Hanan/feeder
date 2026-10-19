"""Simple LAN multiplayer: host runs the game, clients send movement input."""
import json
import queue
import socket
import threading

PORT = 50505
MAX_PLAYERS = 4


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


class LineSocket:
    def __init__(self, sock):
        self.sock = sock
        self._buf = b""

    def send(self, obj):
        self.sock.sendall((json.dumps(obj, separators=(",", ":")) + "\n").encode())

    def recv_line(self):
        while b"\n" not in self._buf:
            chunk = self.sock.recv(8192)
            if not chunk:
                return None
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return json.loads(line.decode())


def _reader(linesock, out_q, on_close):
    try:
        while True:
            msg = linesock.recv_line()
            if msg is None:
                break
            out_q.put(msg)
    finally:
        on_close()
        out_q.put({"type": "_disconnect"})


def _reader_host(linesock, out_q):
    try:
        while True:
            msg = linesock.recv_line()
            if msg is None:
                break
            out_q.put((linesock, msg))
    finally:
        out_q.put((None, {"type": "_disconnect"}))


class MultiHost:
    def __init__(self, host_name, host_fav):
        self.in_q = queue.Queue()
        self.players = [{"slot": 0, "name": host_name, "fav": host_fav}]
        self.next_slot = 1
        self.client_slots = {}  # linesock id -> slot
        self._linesocks = []
        self._sock_to_slot = {}
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("", PORT))
        self._srv.listen(MAX_PLAYERS - 1)
        self._srv.settimeout(0.0)
        self._inputs = {}  # slot -> (mx, my)
        self._inputs[0] = (0, 0)
        self.started = False

    @property
    def address(self):
        return local_ip(), PORT

    def set_host_input(self, mx, my):
        self._inputs[0] = (mx, my)

    def poll(self):
        try:
            conn, _ = self._srv.accept()
        except (BlockingIOError, socket.timeout, OSError):
            conn = None
        if conn:
            conn.settimeout(None)
            ls = LineSocket(conn)
            self._linesocks.append(ls)
            threading.Thread(target=_reader_host, args=(ls, self.in_q), daemon=True).start()

        while True:
            try:
                ls, msg = self.in_q.get_nowait()
            except queue.Empty:
                break
            if ls is None and msg.get("type") == "_disconnect":
                continue
            self._handle(ls, msg)

    def _handle(self, ls, msg):
        t = msg.get("type")
        if t == "join":
            if self.started or len(self.players) >= MAX_PLAYERS:
                return
            slot = self.next_slot
            self.next_slot += 1
            self.players.append({"slot": slot, "name": msg.get("name", f"P{slot}"), "fav": msg.get("fav", "apple")})
            self._inputs[slot] = (0, 0)
            self._sock_to_slot[ls] = slot
            try:
                ls.send({"type": "welcome", "slot": slot, "players": self.players})
            except OSError:
                pass
            self._broadcast({"type": "lobby", "players": self.players})
        elif t == "input":
            slot = msg.get("slot")
            if slot in self._inputs:
                self._inputs[slot] = (int(msg.get("mx", 0)), int(msg.get("my", 0)))

    def _broadcast(self, obj):
        for ls in self._linesocks:
            try:
                ls.send(obj)
            except OSError:
                pass

    def broadcast_state(self, state):
        if self.started:
            self._broadcast({"type": "state", "state": state})

    def start_game(self):
        self.started = True
        self._broadcast({"type": "start", "players": self.players})

    def get_inputs(self):
        return dict(self._inputs)

    def close(self):
        try:
            self._srv.close()
        except OSError:
            pass
        for ls in self._linesocks:
            try:
                ls.sock.close()
            except OSError:
                pass


class MultiClient:
    def __init__(self, host):
        self.in_q = queue.Queue()
        self.sock = socket.create_connection((host, PORT), timeout=5)
        self.linesock = LineSocket(self.sock)
        self.slot = None
        self.players = []
        self.latest_state = None
        self.started = False
        self.connected = True
        threading.Thread(
            target=_reader,
            args=(self.linesock, self.in_q, self._on_close),
            daemon=True,
        ).start()

    def _on_close(self):
        self.connected = False

    def send_join(self, name, fav):
        self.linesock.send({"type": "join", "name": name, "fav": fav})

    def send_input(self, mx, my):
        if self.slot is None:
            return
        try:
            self.linesock.send({"type": "input", "slot": self.slot, "mx": mx, "my": my})
        except OSError:
            self.connected = False

    def poll(self):
        while True:
            try:
                msg = self.in_q.get_nowait()
            except queue.Empty:
                break
            t = msg.get("type")
            if t == "_disconnect":
                self.connected = False
            elif t == "lobby":
                self.players = msg.get("players", [])
                for p in self.players:
                    if p.get("name") == msg.get("you"):
                        pass
            elif t == "welcome":
                self.slot = msg.get("slot")
                self.players = msg.get("players", [])
            elif t == "start":
                self.started = True
                self.players = msg.get("players", [])
            elif t == "state":
                self.latest_state = msg.get("state")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
