const W = 1152, H = 648;
const FOODS = ["apple", "banana", "strawberry", "carrot", "tomato", "eggplant", "avocado", "kiwi"];
const FOOD_COLORS = {
  apple: "#dc3232", banana: "#f5dc3c", strawberry: "#e62846", carrot: "#f0821e",
  tomato: "#eb5a46", eggplant: "#8246aa", avocado: "#6ea03c", kiwi: "#8cb432",
};

let room = "";
let mySlot = null;
let amHost = false;
let selectedFav = "apple";
let state = null;
let keys = { up: false, down: false, left: false, right: false };
const foodImgs = {};
let bgImg = null;

let peer = null;
let hostSim = null;
const peers = new Map(); // conn -> slot
let hostConn = null;
let tickTimer = null;
let faceDataUrl = null;
const faceCache = new Map(); // slot -> HTMLImageElement
const faceCacheSrc = new Map(); // slot -> data url

function $(id) { return document.getElementById(id); }
function show(id) {
  ["screen-home", "screen-lobby", "screen-game"].forEach(s => $(s).classList.add("hidden"));
  $(id).classList.remove("hidden");
}

function roomFromUrl() {
  return (new URLSearchParams(location.search).get("room") || "").toUpperCase();
}

function hostSecretFor(code) {
  return new URLSearchParams(location.search).get("h")
    || sessionStorage.getItem(`hostSecret:${code}`);
}

function shareUrl(code) {
  const u = new URL(location.origin + location.pathname);
  u.searchParams.set("room", code);
  const secret = hostSecretFor(code);
  if (secret) u.searchParams.set("h", secret);
  return u.href;
}

function randomCode(len = 5) {
  const c = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let s = "";
  for (let i = 0; i < len; i++) s += c[Math.floor(Math.random() * c.length)];
  return s;
}

function peerHostId(code) {
  const secret = hostSecretFor(code);
  if (!secret) return null;
  return `feedfaces-${code}-${secret}`;
}

function isRoomHost(code) {
  return sessionStorage.getItem(`hostOwner:${code}`) === "1";
}

function newHostSecret(code) {
  const secret = randomCode(5) + randomCode(5);
  sessionStorage.setItem(`hostOwner:${code}`, "1");
  sessionStorage.setItem(`hostSecret:${code}`, secret);
  return secret;
}

function createRoom() {
  room = randomCode();
  newHostSecret(room);
  $("share-link").value = shareUrl(room);
  $("create-result").classList.remove("hidden");
}

function enterLobby() {
  history.replaceState(null, "", shareUrl(room));
  amHost = isRoomHost(room);
  setupLobby();
}

const PEER_OPTS = {
  config: {
    iceServers: [
      { urls: "stun:stun.l.google.com:19302" },
      { urls: "stun:stun1.l.google.com:19302" },
    ],
  },
};

function destroyPeer() {
  if (peer) {
    try { peer.destroy(); } catch (_) {}
    peer = null;
  }
  hostConn = null;
  peers.clear();
}

function setLobbyStatus(msg) {
  $("lobby-status").textContent = msg;
}

function updateFacePreview() {
  const img = $("face-preview");
  const ph = $("face-placeholder");
  if (faceDataUrl) {
    img.src = faceDataUrl;
    img.classList.remove("hidden");
    ph.classList.add("hidden");
  } else {
    img.classList.add("hidden");
    ph.classList.remove("hidden");
  }
}

/** Remove black backdrop (edge flood-fill), keep face/hair shape as-is */
function removeBlackBackground(ctx, w, h) {
  const img = ctx.getImageData(0, 0, w, h);
  const d = img.data;
  const bg = new Uint8Array(w * h);
  const q = [];

  const isBlack = (i) => {
    const r = d[i];
    const g = d[i + 1];
    const b = d[i + 2];
    const a = d[i + 3];
    if (a < 8) return true;
    return r <= 42 && g <= 42 && b <= 42;
  };

  const push = (x, y) => {
    if (x < 0 || y < 0 || x >= w || y >= h) return;
    const p = y * w + x;
    if (bg[p]) return;
    if (!isBlack(p * 4)) return;
    bg[p] = 1;
    q.push(p);
  };

  for (let x = 0; x < w; x++) {
    push(x, 0);
    push(x, h - 1);
  }
  for (let y = 0; y < h; y++) {
    push(0, y);
    push(w - 1, y);
  }
  while (q.length) {
    const p = q.pop();
    const x = p % w;
    const y = (p / w) | 0;
    push(x + 1, y);
    push(x - 1, y);
    push(x, y + 1);
    push(x, y - 1);
  }
  for (let p = 0; p < w * h; p++) {
    if (bg[p]) d[p * 4 + 3] = 0;
  }
  ctx.putImageData(img, 0, 0);
}

function processFaceBitmap(bmp) {
  const work = 384;
  const c = document.createElement("canvas");
  c.width = c.height = work;
  const g = c.getContext("2d");
  g.clearRect(0, 0, work, work);
  const scale = Math.min(work / bmp.width, work / bmp.height);
  const dw = bmp.width * scale;
  const dh = bmp.height * scale;
  g.drawImage(bmp, (work - dw) / 2, (work - dh) / 2, dw, dh);
  removeBlackBackground(g, work, work);
  const trimmed = trimTransparent(c);
  return trimmed.toDataURL("image/png");
}

function trimTransparent(canvas) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const data = ctx.getImageData(0, 0, w, h).data;
  let minX = w, minY = h, maxX = 0, maxY = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (data[(y * w + x) * 4 + 3] > 12) {
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
      }
    }
  }
  if (maxX <= minX) return canvas;
  const pad = 4;
  minX = Math.max(0, minX - pad);
  minY = Math.max(0, minY - pad);
  maxX = Math.min(w - 1, maxX + pad);
  maxY = Math.min(h - 1, maxY + pad);
  const tw = maxX - minX + 1;
  const th = maxY - minY + 1;
  const out = document.createElement("canvas");
  out.width = tw;
  out.height = th;
  out.getContext("2d").drawImage(canvas, minX, minY, tw, th, 0, 0, tw, th);
  return out;
}

async function loadFaceFromFile(file) {
  if (!file || !file.type.startsWith("image/")) return;
  const bmp = await createImageBitmap(file);
  faceDataUrl = processFaceBitmap(bmp);
  updateFacePreview();
}

const INK = "#141414";

function photoLayout(img, headSize) {
  const iw = img.naturalWidth || 1;
  const ih = img.naturalHeight || 1;
  const scale = headSize / Math.max(iw, ih);
  return { dw: iw * scale, dh: ih * scale };
}

/** Default stick-man head: round face with simple eyes & smile */
function drawDefaultHead(ctx, x, headY, radius, color) {
  ctx.fillStyle = color || "#f0c896";
  ctx.beginPath();
  ctx.arc(x, headY, radius, 0, Math.PI * 2);
  ctx.fill();
  const eye = radius * 0.11;
  ctx.fillStyle = INK;
  ctx.beginPath();
  ctx.arc(x - radius * 0.32, headY - radius * 0.15, eye, 0, Math.PI * 2);
  ctx.arc(x + radius * 0.32, headY - radius * 0.15, eye, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = INK;
  ctx.lineWidth = Math.max(2, radius * 0.06);
  ctx.beginPath();
  ctx.arc(x, headY + radius * 0.08, radius * 0.38, 0.2 * Math.PI, 0.8 * Math.PI);
  ctx.stroke();
}

/** Uploaded cutout only — natural head/hair shape, no circle */
function drawPhotoHead(ctx, img, x, headY, headSize) {
  const { dw, dh } = photoLayout(img, headSize);
  ctx.drawImage(img, x - dw / 2, headY - dh / 2, dw, dh);
}

function strokeHeadOutline(ctx, x, headY, radius) {
  ctx.strokeStyle = INK;
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.arc(x, headY, radius, 0, Math.PI * 2);
  ctx.stroke();
}

function syncRunnerFaces(runners) {
  (runners || []).forEach(r => {
    if (!r.face) return;
    if (faceCacheSrc.get(r.slot) === r.face) return;
    faceCacheSrc.set(r.slot, r.face);
    const im = new Image();
    im.onload = () => faceCache.set(r.slot, im);
    im.crossOrigin = "anonymous";
    im.src = r.face;
  });
}

function setupLobby() {
  show("screen-lobby");
  $("lobby-code").textContent = room;
  const hasSecret = !!hostSecretFor(room);
  if (amHost) {
    setLobbyStatus("You are the host — click Join room to open the lobby for friends.");
    $("lobby-hint").textContent = "Share Copy link, then Join room here before friends connect.";
  } else if (!hasSecret) {
    setLobbyStatus("Missing invite key — open the host's full link, not just the room code.");
    $("lobby-hint").textContent = "URL must include ?room=…&h=…";
  } else {
    setLobbyStatus("Pick your name and food, then Join room.");
    $("lobby-hint").textContent = "Host must click Join room first and keep their tab open.";
  }
  updateFacePreview();
  const pick = $("food-pick");
  pick.innerHTML = "";
  FOODS.forEach(f => {
    const b = document.createElement("button");
    b.type = "button";
    const img = document.createElement("img");
    img.src = `/assets/foods/${f}.png`;
    img.alt = f;
    img.width = 44;
    img.height = 44;
    b.appendChild(img);
    b.onclick = () => {
      selectedFav = f;
      pick.querySelectorAll("button").forEach(x => x.classList.remove("selected"));
      b.classList.add("selected");
    };
    if (f === selectedFav) b.classList.add("selected");
    pick.appendChild(b);
  });
}

function broadcast(msg) {
  const data = JSON.stringify(msg);
  if (amHost) {
    peers.forEach(conn => { try { conn.send(data); } catch (_) {} });
  } else if (hostConn?.open) {
    try { hostConn.send(data); } catch (_) {}
  }
}

function renderPlayerList(players) {
  const ul = $("player-list");
  ul.innerHTML = "";
  (players || []).forEach(p => {
    const li = document.createElement("li");
    li.textContent = `${p.name} — ${p.fav}`;
    ul.appendChild(li);
  });
}

function onJoined(slot, players) {
  mySlot = slot;
  $("btn-ready").classList.add("hidden");
  $("lobby-status").textContent = amHost
    ? "You are the host — friends must open your link."
    : "In lobby — waiting for host to start…";
  $("btn-start").classList.toggle("hidden", !amHost);
  $("lobby-hint").textContent = amHost
    ? "1) Copy link  2) Friends open it  3) They click Join room  4) You press Start"
    : "Host must click Join room first, then you can connect.";
  renderPlayerList(players);
}

function handleHostMessage(conn, raw) {
  let msg;
  try { msg = JSON.parse(raw); } catch (_) { return; }
  if (msg.type === "join" && hostSim && !hostSim.started) {
    const p = hostSim.addPlayer(msg.name, msg.fav, msg.face || null);
    if (!p) return;
    peers.set(conn, p.slot);
    conn.send(JSON.stringify({
      type: "joined", slot: p.slot, is_host: false,
      players: hostSim.playerList(),
    }));
    broadcast({ type: "lobby", players: hostSim.playerList() });
  }
  if (msg.type === "input" && hostSim?.started && msg.slot != null) {
    hostSim.inputs[msg.slot] = [msg.mx, msg.my];
  }
}

function startHostPeer(name, fav, retry = 0) {
  destroyPeer();
  hostSim = new Sim.Room();
  const me = hostSim.addPlayer(name, fav, faceDataUrl);
  mySlot = me.slot;
  amHost = true;

  let id = peerHostId(room);
  if (!id) {
    newHostSecret(room);
    history.replaceState(null, "", shareUrl(room));
    $("share-link").value = shareUrl(room);
    id = peerHostId(room);
  }

  setLobbyStatus("Opening lobby for friends…");
  peer = new Peer(id, PEER_OPTS);
  peer.on("open", () => {
    setLobbyStatus("Lobby is open — friends can join with your copied link.");
    $("share-link").value = shareUrl(room);
    onJoined(mySlot, hostSim.playerList());
  });
  peer.on("connection", conn => {
    conn.on("data", data => handleHostMessage(conn, data));
  });
  peer.on("error", err => {
    console.error(err);
    if (err.type === "unavailable-id" && retry < 3) {
      newHostSecret(room);
      history.replaceState(null, "", shareUrl(room));
      $("share-link").value = shareUrl(room);
      startHostPeer(name, fav, retry + 1);
      return;
    }
    setLobbyStatus("Could not open lobby — refresh and try Create game again.");
  });
}

function attachGuestHandlers(name, fav, conn) {
  conn.on("data", data => {
    let msg;
    try { msg = JSON.parse(data); } catch (_) { return; }
    if (msg.type === "joined") onJoined(msg.slot, msg.players);
    if (msg.type === "lobby") renderPlayerList(msg.players);
    if (msg.type === "start") {
      state = msg.state;
      syncRunnerFaces(state.runners);
      WinFX.reset();
      loopT = 0;
      show("screen-game");
      requestAnimationFrame(loop);
    }
    if (msg.type === "state") {
      state = msg.state;
      syncRunnerFaces(state.runners);
    }
  });
  conn.on("open", () => {
    conn.send(JSON.stringify({ type: "join", name, fav, face: faceDataUrl }));
  });
  conn.on("close", () => {
    if (!$("screen-game").classList.contains("hidden")) {
      alert("Disconnected from host.");
      show("screen-home");
    }
  });
}

function startGuestPeer(name, fav) {
  if (!hostSecretFor(room)) {
    setLobbyStatus("Use the host's full invite link (Copy link), not just the room code.");
    alert("Open the full URL from the host. It should include ?room=…&h=…");
    return;
  }
  destroyPeer();
  setLobbyStatus("Connecting to host…");

  peer = new Peer(undefined, PEER_OPTS);
  let attempt = 0;
  let poll = null;
  let pendingConn = null;

  function dial() {
    if (mySlot != null || !peer || peer.destroyed) return;
    const targetId = peerHostId(room);
    if (!targetId) return;
    if (pendingConn && !pendingConn.open) return;
    if (hostConn?.open) return;
    if (pendingConn) {
      try { pendingConn.close(); } catch (_) {}
    }
    pendingConn = peer.connect(targetId, { reliable: true });
    hostConn = pendingConn;
    attachGuestHandlers(name, fav, pendingConn);
  }

  peer.on("open", () => {
    dial();
    poll = setInterval(() => {
      if (mySlot != null) {
        clearInterval(poll);
        return;
      }
      if (hostConn?.open) return;
      attempt += 1;
      setLobbyStatus(`Waiting for host lobby… (${attempt}) — host must click Join room`);
      if (attempt >= 30) {
        clearInterval(poll);
        setLobbyStatus("No host found. Ask them to Join room and keep this tab open.");
        return;
      }
      pendingConn = null;
      dial();
    }, 2500);
  });
  peer.on("error", (err) => {
    console.error(err);
    setLobbyStatus("Connection error — host should refresh and send a new Copy link.");
  });
}

function joinRoom() {
  const name = $("player-name").value.trim() || "Player";
  if (amHost) startHostPeer(name, selectedFav);
  else startGuestPeer(name, selectedFav);
}

function startGame() {
  if (!amHost || !hostSim) return;
  if (!hostSim.start()) return;
  state = hostSim.publicState();
  syncRunnerFaces(state.runners);
  broadcast({ type: "start", state });
  WinFX.reset();
  loopT = 0;
  show("screen-game");
  if (tickTimer) clearInterval(tickTimer);
  tickTimer = setInterval(() => {
    hostSim.step(1 / 30);
    state = hostSim.publicState();
    syncRunnerFaces(state.runners);
    broadcast({ type: "state", state });
  }, 1000 / 30);
  requestAnimationFrame(loop);
}

function sendInput() {
  if (!state?.started) return;
  const mx = (keys.right ? 1 : 0) - (keys.left ? 1 : 0);
  const my = (keys.down ? 1 : 0) - (keys.up ? 1 : 0);
  if (amHost && hostSim && mySlot != null) {
    hostSim.inputs[mySlot] = [mx, my];
  } else if (hostConn?.open && mySlot != null) {
    hostConn.send(JSON.stringify({ type: "input", mx, my, slot: mySlot }));
  }
}

document.addEventListener("keydown", (e) => {
  if (["ArrowUp", "w", "W"].includes(e.key)) keys.up = true;
  if (["ArrowDown", "s", "S"].includes(e.key)) keys.down = true;
  if (["ArrowLeft", "a", "A"].includes(e.key)) keys.left = true;
  if (["ArrowRight", "d", "D"].includes(e.key)) keys.right = true;
  sendInput();
});
document.addEventListener("keyup", (e) => {
  if (["ArrowUp", "w", "W"].includes(e.key)) keys.up = false;
  if (["ArrowDown", "s", "S"].includes(e.key)) keys.down = false;
  if (["ArrowLeft", "a", "A"].includes(e.key)) keys.left = false;
  if (["ArrowRight", "d", "D"].includes(e.key)) keys.right = false;
  sendInput();
});
setInterval(sendInput, 50);

$("btn-create").onclick = createRoom;
$("btn-copy").onclick = () => {
  $("share-link").select();
  navigator.clipboard?.writeText($("share-link").value);
};
$("btn-enter-lobby").onclick = enterLobby;
$("btn-ready").onclick = joinRoom;
$("btn-start").onclick = startGame;
$("face-file").onchange = (e) => {
  const f = e.target.files?.[0];
  if (f) loadFaceFromFile(f);
};
$("face-clear").onclick = () => {
  faceDataUrl = null;
  $("face-file").value = "";
  updateFacePreview();
};

const canvas = $("game");
const ctx = canvas.getContext("2d");

function loadImages() {
  bgImg = new Image();
  bgImg.src = "/assets/background.png";
  FOODS.forEach(f => {
    const im = new Image();
    im.src = `/assets/foods/${f}.png`;
    foodImgs[f] = im;
  });
}
loadImages();

function drawRunner(r) {
  if (r.burst) return;
  const x = r.x, y = r.y;
  const swing = r.moving ? Math.sin(r.run_t) * 0.9 : 0;
  const hs = r.head_size || 70;
  ctx.strokeStyle = "#141414";
  ctx.lineWidth = 5;
  ctx.fillStyle = "rgba(70,50,35,.5)";
  ctx.beginPath();
  ctx.ellipse(x, y - 5, 24, 6, 0, 0, Math.PI * 2);
  ctx.fill();
  const hipY = y - 38 * 0.55, shY = y - 38;
  ctx.beginPath();
  ctx.moveTo(x, hipY);
  ctx.lineTo(x, shY);
  ctx.stroke();
  [-1, 1].forEach(s => {
    const fx = x + s * swing * 34, fy = y;
    ctx.beginPath();
    ctx.moveTo(x, hipY);
    ctx.lineTo((x + fx) / 2 + r.facing * 6, (hipY + fy) / 2);
    ctx.lineTo(fx, fy);
    ctx.stroke();
    const hx = x + s * 22 - s * swing * 12, hy = shY + 12 + swing * s * 8;
    ctx.beginPath();
    ctx.moveTo(x, shY);
    ctx.lineTo((x + hx) / 2, (shY + hy) / 2 + 4);
    ctx.lineTo(hx, hy);
    ctx.stroke();
  });
  const headY = y - 38 - hs * 0.52;
  const radius = hs / 2;
  const faceImg = faceCache.get(r.slot);
  const hasFace = faceImg?.complete && faceImg.naturalWidth && r.face;

  if (hasFace) {
    drawPhotoHead(ctx, faceImg, x, headY, hs);
    if (r.flash > 0) {
      ctx.save();
      ctx.globalAlpha = 0.4;
      ctx.fillStyle = "#ff5a5a";
      const { dw, dh } = photoLayout(faceImg, hs);
      ctx.fillRect(x - dw / 2, headY - dh / 2, dw, dh);
      ctx.restore();
    }
  } else {
    drawDefaultHead(ctx, x, headY, radius, r.color);
    if (r.flash > 0) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(x, headY, radius, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(255, 90, 90, 0.45)";
      ctx.fill();
      ctx.restore();
    }
    strokeHeadOutline(ctx, x, headY, radius);
  }
  ctx.fillStyle = "#111";
  ctx.font = "16px system-ui";
  ctx.textAlign = "center";
  ctx.fillText(`${r.name}  ${Math.max(0, r.count)}/5`, x, y + 22);
}

function drawMeal(m, highlight) {
  const [mx, my] = m.pos;
  const cx = mx, cy = my - 21;
  const img = foodImgs[m.name];
  if (img?.complete) ctx.drawImage(img, cx - 30, cy - 30, 60, 60);
  else {
    ctx.fillStyle = FOOD_COLORS[m.name] || "#ccc";
    ctx.beginPath();
    ctx.arc(cx, cy, 24, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.fillStyle = highlight ? "#ffffc8" : "#fff";
  ctx.beginPath();
  ctx.ellipse(mx, my - 6, 20, 6, 0, 0, Math.PI * 2);
  ctx.fill();
}

function runnerHeadXY(r) {
  const hs = r.head_size || 70;
  return { x: r.x, y: r.y - 38 - hs * 0.52 };
}

let loopT = 0;
function loop(t) {
  if (!state?.runners) {
    requestAnimationFrame(loop);
    return;
  }
  const dt = Math.min(0.05, loopT ? (t - loopT) / 1000 : 0.016);
  loopT = t;

  syncRunnerFaces(state.runners);
  if (bgImg?.complete) ctx.drawImage(bgImg, 0, 0, W, H);
  else { ctx.fillStyle = "#c8e6be"; ctx.fillRect(0, 0, W, H); }
  const sorted = [...state.runners].sort((a, b) => a.y - b.y);
  sorted.forEach(r => { if (r.meal) drawMeal(r.meal, r.slot === mySlot); });
  sorted.forEach(drawRunner);

  if (state.winner_slot != null) {
    const w = state.runners.find(r => r.slot === state.winner_slot);
    if (w) {
      const hp = runnerHeadXY(w);
      WinFX.spawn(state.winner_slot, hp.x, hp.y);
    }
    WinFX.update(dt);
    WinFX.draw(ctx);
    ctx.fillStyle = "rgba(0,0,0,.35)";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#ffdd55";
    ctx.font = "bold 58px system-ui";
    ctx.textAlign = "center";
    ctx.strokeStyle = "#8b2020";
    ctx.lineWidth = 4;
    const msg = `${w?.name || "Someone"} wins!`;
    ctx.strokeText(msg, W / 2, H / 2);
    ctx.fillText(msg, W / 2, H / 2);
  } else {
    WinFX.reset();
  }
  requestAnimationFrame(loop);
}

room = roomFromUrl();
if (room) {
  const urlSecret = new URLSearchParams(location.search).get("h");
  if (urlSecret) sessionStorage.setItem(`hostSecret:${room}`, urlSecret);
  amHost = isRoomHost(room);
  setupLobby();
} else {
  show("screen-home");
}
