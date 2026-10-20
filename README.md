# feeder

Feed the Faces — browser game (Vercel / bots) and desktop Pygame version.

## Arduino UNO Q

Run on the board’s **Linux** side (1280×720 display). Same gameplay; embedded build uses smaller assets and skips PeerJS on startup.

See **[ARDUINO_UNO_Q.md](ARDUINO_UNO_Q.md)** — `npm run build:uno-q` then `./scripts/run-uno-q.sh`.

## Browser (Vercel / local)

```bash
npm run build
cd public && python3 -m http.server 8080
```

Open http://localhost:8080

## Desktop

```bash
pip3 install pygame
python3 game.py
```
