# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KaTrain is a Go/Baduk/Weiqi teaching and analysis tool. It communicates with the KataGo engine (via subprocess/JSON protocol) for AI analysis and provides a Kivy/KivyMD GUI for board display, game review, and playing against various AI opponents.

## Common Commands

```bash
uv run pytest tests                  # Run all tests
uv run pytest tests/test_board.py    # Run a single test file
uv run pytest tests/test_board.py -k "test_name"  # Run a specific test
uv run black .                       # Format code (120 char line length)
uv run python i18n.py -todo          # Check for missing translations
uv build                             # Build package
uv run python -m katrain             # Run the app
```

## Architecture

### Core (`katrain/core/`)
- **engine.py** - KataGo subprocess management and JSON analysis protocol
- **game.py** - Board state, move validation, capture/scoring logic
- **game_node.py** - SGF game tree node (parent/children tree structure with dict-like properties)
- **sgf_parser.py** - SGF file parsing and writing (supports GTP and SGF coordinate systems)
- **ai.py** - AI strategy implementations using a decorator-based registry (`@register_strategy`). Strategies range from full-strength KataGo to various weakened/styled play (policy-weighted, local, tenuki, territory, influence, rank-calibrated, etc.)
- **base_katrain.py** - Base class providing settings, logging, and player management
- **constants.py** - All game mode constants, AI strategy identifiers, priority levels

### GUI (`katrain/gui/`)
- **`__main__.py`** - Main `KaTrainApp(MDApp)` class. Uses a message queue pattern for thread-safe game state updates between the analysis engine and UI
- **badukpan.py** - Go board rendering widget (stone drawing, annotations, coordinates)
- **popups.py** - Modal dialogs (settings, file browser, game info)
- **gui.kv / popups.kv** - Kivy KV language files defining UI layout and widget hierarchy
- **widgets/** - Specialized UI components (move tree, analysis graphs, file browser)

### Key Data Flow
1. User action or AI move → `KaTrainApp` processes via message queue
2. Move sent to KataGo engine subprocess → JSON analysis response
3. Analysis results stored in `GameNode` tree → UI updates reactively
4. Game state is an SGF tree; navigation = moving between `GameNode`s

### Other Directories
- `katrain/KataGo/` - Bundled KataGo engine binaries per platform
- `katrain/models/` - Neural network model files
- `katrain/i18n/` - Translation `.po` files
- `themes/` - Custom UI theme configurations

## Code Style

- **Black** with 120 char line length (configured in pyproject.toml)
- **Flake8** ignores: E501, E203, W503, E402 (see .flake8)
- Python 3.9–3.13; use modern type annotations (`list[int]` not `List[int]`)
- User config stored at `~/.katrain/`, app default config in `katrain/config.json`

## Entry Point

`katrain/__main__.py:run_app()` — creates `KaTrainApp` (Kivy App), sets up signal handling and exception handler, then calls `app.run()`.

## Visual Testing (Screenshot the running app)

To visually verify GUI changes, launch the app, capture a screenshot of the window, then kill it:

```bash
uv run python -m katrain &
APP_PID=$!
sleep 6
WID=$(swift -e "
import Cocoa
let windows = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]] ?? []
for w in windows {
    let name = w[kCGWindowName as String] as? String ?? \"\"
    if name.contains(\"KaTrain\") {
        print(w[kCGWindowNumber as String] as? Int ?? 0)
        break
    }
}
" 2>/dev/null)
screencapture -x -o -l "$WID" /tmp/katrain_win.png
kill $APP_PID 2>/dev/null
wait $APP_PID 2>/dev/null
```

Then use `Read` on `/tmp/katrain_win.png` to view the screenshot.
