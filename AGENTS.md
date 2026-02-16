# AGENTS.md

Practical guidance for AI agents (and humans) working in this KaTrain repository.

This repo is a Kivy/KivyMD desktop app for Go/Baduk analysis that talks to a KataGo engine subprocess.

## Quick Commands

Use `uv` for Python commands in this repo:

```bash
uv run pytest tests
uv run pytest tests/test_board.py -k "some_test_name"
uv run black .
uv run python -m katrain
```

## Codebase Map (Where Things Live)

- `katrain/core/`: game logic, SGF tree, engine protocol, AI strategies
- `katrain/gui/`: Kivy/KivyMD UI, KV files, widgets, popups
- `katrain/__main__.py`: app entry point and UI <-> engine message queue
- `tests/`: pytest suite

## Local Conventions (Keep Noise Down)

- Prefer modern type annotations (`list[int]`, `dict[str, int]`).
- Do not add `if TYPE_CHECKING:` blocks (too noisy here).
- Do not add `__all__` except at the *top-level* `__init__.py` of a package.
- Avoid overly-defensive patterns; if something is wrong, a loud exception is fine. However, keep in mind this is a non technical user facing UI, so expected errors (network blips etc) should be surfaced in the UI.

## Visual Testing: Start -> Screenshot -> Read (Fast Loop)

For UI work, the quickest feedback loop is:

1. Start KaTrain in the background.
2. Screenshot the app window to a known file path.
3. Read the screenshot directly in the IDE (Cursor can open images via file-read tools).
4. Kill the app.

### Prefer the helper script

Use `scripts/run_and_screenshot.sh` instead of copy/pasting a one-off snippet.

It exists mainly so you can run the loop yourself from a normal terminal, without an agent
re-running privileged commands (which typically triggers repeated approval prompts).

```bash
# Default: run KaTrain and screenshot it.
scripts/run_and_screenshot.sh

# Screenshot a small harness app (faster iteration on a widget/layout):
scripts/run_and_screenshot.sh test_button.py

# Or run an arbitrary command (everything after --):
scripts/run_and_screenshot.sh --out screenshots/foo.png -- uv run python -m katrain
```

The script writes logs to:

- `/tmp/run_and_screenshot_stdout.log`
- `/tmp/run_and_screenshot_stderr.log`

### If screenshots fail on macOS

macOS may require Screen Recording permission for your terminal/IDE to take screenshots.
The error usually looks like `could not create image from window`.

### Reading the screenshot in Cursor

- Open `screenshots/_katrain_last.png` and view it directly, or
- If you are using an agent that can read files, have it read that path with the image-capable reader.

### Tight iteration tips

- Keep the output path constant (e.g. `screenshots/_katrain_last.png`) so you can re-open the same tab.
- If you need to capture multiple states, add a short `sleep` and take 2-3 screenshots with different names.
- If you're iterating on a single widget/layout, make a tiny harness app (like `test_button.py`) to avoid click-through and engine startup time.

