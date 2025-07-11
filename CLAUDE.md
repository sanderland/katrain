# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KaTrain is a Go/Baduk/Weiqi playing and teaching application that integrates with KataGo AI. It provides game analysis, AI teaching modes, and various playing styles. The application is built with Python and Kivy for cross-platform GUI support.

## Development Commands

### Running the Application
```bash
# Run directly without installing
python3 -m katrain

# Run after installation
katrain
```

### Installation and Dependencies
```bash
# Install for development (with UV)
uv pip install -e .

# Install for development (with pip)
pip3 install -e .

# Install production
pip3 install .
```

### Code Quality
```bash
# Format code (required before commits)
black -l 120 .

# Run tests
pytest

# Run specific test
pytest tests/test_filename.py::test_function_name
```

### Building and Distribution
```bash
# Build translations
python3 i18n.py

# Create executable for current platform
pyinstaller spec/KaTrain.spec

# The executable will be in dist/
```

## Architecture Overview

### Core Components

1. **Entry Points**
   - `katrain/__main__.py`: Main application entry point
   - `katrain.py`: Backward compatibility wrapper

2. **Game Engine Integration**
   - `katrain/core/engine.py`: KataGo engine wrapper and communication
   - `katrain/core/ai.py`: AI move generation and analysis
   - Engine binaries are in `katrain/KataGo/` directory

3. **Game Logic**
   - `katrain/core/game.py`: Game state management and move validation
   - `katrain/core/sgf_parser.py`: SGF file parsing and generation
   - `katrain/core/game_node.py`: Game tree node implementation

4. **GUI Architecture**
   - Built on Kivy with KivyMD for Material Design
   - `katrain/gui.kv`: Main UI layout definition
   - `katrain/gui/badukpan.py`: Board widget implementation
   - `katrain/gui/controlspanel.py`: Control panels and game controls
   - Event-driven architecture with Kivy properties and bindings

5. **Internationalization**
   - `katrain/i18n/`: Translation system
   - `katrain/i18n/locales/`: Language files (11 languages)
   - Uses gettext-style translations

### Key Design Patterns

1. **BaseKatrain Class**: Central application class that coordinates between GUI and game logic
2. **Engine Communication**: Asynchronous communication with KataGo using subprocess
3. **Property Binding**: Extensive use of Kivy properties for reactive UI updates
4. **SGF Handling**: Complete SGF parser with support for variations and annotations

## Platform-Specific Considerations

### macOS (Metal)
- Requires pygame for proper window handling
- KataGo binary uses Metal acceleration when available
- Build system creates .app bundle via PyInstaller

### Build Configuration
- PyInstaller specs in `spec/` directory handle platform-specific packaging
- Binary inclusion handled automatically based on platform

## Testing Approach

- Unit tests in `tests/` directory using pytest
- Tests cover SGF parsing, game logic, and engine communication
- GUI testing is limited due to Kivy's event loop requirements

## Common Development Tasks

### Adding New Features
1. Game logic goes in `katrain/core/`
2. GUI components go in `katrain/gui/`
3. Update translations in `katrain/i18n/locales/`
4. Add tests in `tests/`

### Modifying AI Behavior
- AI personalities defined in `katrain/core/ai.py`
- Engine parameters in `katrain/core/engine.py`
- Config templates in `katrain/KataGo/`

### UI Modifications
- Main layout in `katrain/gui.kv`
- Popup layouts in `katrain/popups.kv`
- Theme modifications in `themes/` directory
- Custom widgets in `katrain/gui/widgets/`

## Important Files and Paths

- `katrain/core/constants.py`: Application constants and defaults
- `katrain/config.json`: User configuration (generated at runtime)
- `~/.katrain/`: User data directory (games, settings, etc.)
- `katrain/models/`: Neural network models for KataGo