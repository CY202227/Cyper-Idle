# Cyber-Idle

A cyberpunk-themed idle game implemented in Python (**PyScript in the browser**).

[English](README.md) | [简体中文](README.zh-CN.md)

---

## How to run (important)

This project is a **static web app**, same as GitHub Pages:

| Do | Don't |
|----|--------|
| Serve the **repo root** over HTTP and open `index.html` in a browser | Run `python python/main.py` |
| Use PyScript’s browser `js` / `document` APIs | `pip install js` (wrong package) |

### Play online (GitHub Pages)

1. Push this repo to GitHub.
2. **Settings → Pages → Deploy from branch** (usually `main` / `/` root).
3. Open `https://<user>.github.io/<repo>/`.

Pages serves [`index.html`](index.html), which loads [`python/main.py`](python/main.py) via PyScript (`<script type="py" …>`).

### Play locally (same model as Pages)

From the **repository root** (not inside `python/`):

```bash
python -m http.server 8000
```

Then open **http://localhost:8000** in your browser.

---

## Features

- **Pure Frontend**: PyScript; no game backend.
- **Cyberpunk UI**: CRT / glitch styling.
- **Save System**: `localStorage` + Base64 export/import.
- **Multi-language**: English / Chinese JSON content.
- **Story-Driven**: Branching nodes with resource gates.
- **Dungeon Exploration**: Procedural subnets + **auto-explore**.
- **Network Warfare**: Auto offense/defense with live stability bars.
- **Network Ops**: Timed bandwidth actions (no daemon/pet system).
- **Online-only idle**: No offline earnings catch-up.

## Project Structure

```text
/
├── index.html          # Entry (PyScript loads main.py)
├── pyscript.json       # Files fetched into the browser runtime
├── css/style.css
├── data/               # en / zh configs
└── python/             # Game logic (runs in browser, not as CLI)
```

## License

MIT
