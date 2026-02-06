# Cyber-Idle

A cyberpunk-themed idle game implemented in Python (PyScript).

[English](README.md) | [简体中文](README.zh-CN.md)

---

## 🌟 Features

- **Pure Frontend**: Runs directly in the browser using PyScript, no backend server required.
- **Cyberpunk UI**: Minimalist high-contrast color scheme with CRT scanlines and Glitch effects.
- **No-DB Save System**: Progress is auto-saved to `localStorage`. Supports Evolve-style Base64 string export/import.
- **Multi-language Support**: Built-in English and Chinese toggle. All content (resources, story, events) is easily extendable via JSON.
- **Seeded RNG**: Uses a seeded random number generator for consistent and predictable random events.
- **Story-Driven**: Includes a basic story engine supporting node jumping and branching choices based on resource requirements.

## 🚀 Quick Start

### Play Online
1. Push this project to a GitHub repository.
2. Enable **GitHub Pages** in the repository settings.
3. Visit the generated URL to start playing.

### Run Locally
1. Ensure you have a Python environment installed.
2. Run a static server in the root directory:
   ```bash
   python -m http.server 8000
   ```
3. Visit `http://localhost:8000` in your browser.

## 🛠️ Project Structure

```text
/
├── index.html          # Main entry, loads PyScript environment
├── css/
│   └── style.css       # Cyberpunk styles (CRT, neon colors, animations)
├── data/               # Game configuration files
│   ├── ui.json         # UI translations
│   ├── zh/             # Chinese content (resources, story, events)
│   └── en/             # English content
└── python/             # Core game logic
    ├── main.py         # Initialization, UI binding, and main loop
    ├── engine/         # Game engine (state, resource calculation, story system)
    └── utils/          # Utilities (RNG, storage, i18n)
```

## 📜 License

This project is licensed under the MIT License.
