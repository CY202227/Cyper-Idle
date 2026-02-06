# Cyber-Idle

A cyberpunk-themed idle game implemented using Python (PyScript).

## 🌟 Features

- **Pure Frontend**: Runs directly in the browser using PyScript (Pyodide), no backend server required.
- **Cyberpunk UI**: Minimalist high-contrast color scheme with CRT scanline and Glitch text effects.
- **Database-free Storage**: Progress is automatically saved to browser `localStorage`. Supports Evolve-style Base64 string export/import.
- **Multi-language Support**: Built-in Chinese and English switching. All game content (resources, story, events) is easily extensible via JSON.
- **Seeded RNG**: Uses a Seeded Random Number Generator to ensure consistency and predictability of random events.
- **Story-Driven**: Includes a basic story engine supporting node transitions and branching choices based on resource requirements.

## 🚀 Quick Start

### Play Online
1. Push this project to your GitHub repository.
2. Enable **GitHub Pages** in the repository settings.
3. Visit the generated URL to start playing.

### Run Locally
1. Ensure you have a Python environment installed.
2. Run a static server in the project root:
   ```bash
   python -m http.server 8000
   ```
3. Visit `http://localhost:8000` in your browser.

## 🛠️ Project Structure

```text
/
├── index.html          # Main entry, loads PyScript environment
├── css/
│   └── style.css       # Cyberpunk theme styles (CRT, neon colors, animations)
├── data/               # Game configuration files
│   ├── ui.json         # UI translations
│   ├── zh/             # Chinese content (resources, story, events)
│   └── en/             # English content
└── python/             # Core game logic
    ├── main.py         # Initialization, UI binding, and main loop
    ├── engine/         # Game engine (state, resource calculation, story system)
    └── utils/          # Utilities (RNG, storage, i18n)
```

## 📝 Development & Extension

### Adding New Story Nodes
Edit `data/zh/story.json` and `data/en/story.json`:
```json
"node_id": {
    "text": "Story description text",
    "requirements": { "energy": 100 },
    "actions": {
        "action_id": {
            "label": "Action Label",
            "next_node": "target_node_id",
            "reward": { "credits": 10 }
        }
    }
}
```

### Adding New Resources
Edit `data/zh/resources.json` and `data/en/resources.json`:
```json
"new_resource": {
    "name": "Resource Name",
    "auto_gen": 0.5,
    "description": "Resource description"
}
```

## 📜 License

This project is licensed under the MIT License.
