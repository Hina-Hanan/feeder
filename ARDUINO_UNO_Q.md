# Feed the Faces on Arduino UNO Q

The **UNO Q Linux side** (Debian on QRB2210) can run this game in a browser at **1280×720** (recommended). The STM32 MCU is not used for graphics; keep the game on Linux.

Gameplay is unchanged: same speed, bots, and rules. The **embedded build** only reduces load time and RAM (smaller images, no PeerJS until needed, lighter win effects).

## Quick start (on the board)

```bash
git clone https://github.com/Hina-Hanan/feeder.git feed-the-faces
cd feed-the-faces
chmod +x scripts/run-uno-q.sh
./scripts/run-uno-q.sh
```

Connect a **USB-C PD dock** (5 V / 3 A) with DisplayPort + keyboard. Use **4 GB RAM** variant for smoothest kiosk use.

## Manual setup

```bash
# On your PC or on UNO Q:
pip install Pillow   # optional, for smaller asset copies
npm install
npm run build:uno-q

pip3 install -r requirements-web.txt
python3 web_server.py
# Browse to http://<uno-q-ip>:8080/ or use Chromium kiosk (see scripts/run-uno-q.sh)
```

## Build profiles

| Command | Use |
|---------|-----|
| `npm run build` | Vercel / normal web |
| `npm run build:uno-q` | UNO Q: embedded flag + optimized assets |

## Desktop Pygame (optional)

On Debian you can also run:

```bash
pip3 install pygame
python3 game.py
```

Use a monitor on the same USB-C DP setup.

## Tips

- Prefer **wired USB keyboard** or Bluetooth from Linux settings.
- If the tab feels slow, close other apps; embedded build already skips loading PeerJS on startup.
- Multiplayer later: run `web_server.py` and share `http://<board-ip>:8080/?room=CODE` on your LAN.
