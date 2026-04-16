# PySide6 Port Status

This directory is the start of a PySide6 frontend for KaTrain.

Current scope:

- Shared backend no longer requires Kivy for config storage or platform detection.
- `katrain-qt` starts a native Qt window.
- The Qt window can create a game, open/save SGF, render a board, place moves, and navigate variations.
- Live KataGo startup and analysis are wired into the Qt UI.
- The Qt UI shows candidate moves, ownership overlays, node comments, notes, and engine logs.

Not ported yet:

- full settings dialogs
- score graph
- teaching workflow
- asset download/bootstrap flow

Run it with:

```bash
uv run katrain-qt
```

The default `uv run katrain` entrypoint also launches the Qt app.
