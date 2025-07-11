# KaTrain Build System Analysis

## Overview
This document provides a comprehensive analysis of KaTrain's build system, dependencies, and platform-specific requirements for macOS Metal compilation.

## Python Dependencies

### Core Dependencies (from pyproject.toml)
- **Python Version**: 3.9-3.13 (requires-python = ">=3.9,<3.14")
- **pygame~=2.0**: macOS-specific dependency for window handling
- **screeninfo>=0.8.1,<0.9**: Non-macOS platforms only
- **chardet>=5.2.0,<6**: Character encoding detection
- **docutils>=0.21.2**: Documentation utilities
- **ffpyplayer>=4.5.1**: Media player (excluded on macOS in PyInstaller)
- **urllib3>=2.2.2**: HTTP library
- **kivy>=2.3.1**: Core GUI framework
- **kivymd==0.104.1**: Material Design components for Kivy

### Development Dependencies
- **black>=24.8.0,<25**: Code formatter (required, line-length=120)
- **polib>=1.2.0,<2**: Internationalization/translation tools
- **pyinstaller>=6.14.1**: Application bundler
- **pytest>=8.3.2,<9**: Testing framework
- **tomli>=1.2.0**: TOML parser (Python < 3.11 only)

### Build System
- **Backend**: Hatchling (modern Python packaging)
- **Tool**: UV package manager support configured

## KataGo Binary Integration

### Binary Loading Logic (katrain/core/engine.py)
1. **Windows**: `katrain/KataGo/katago.exe`
2. **Linux**: `katrain/KataGo/katago`
3. **macOS**: 
   - Primary: `katrain/KataGo/katago-osx` (bundled)
   - Fallback: System `katago` (e.g., from Homebrew)
   - Special handling for ARM64 Macs

### Platform Detection
- Uses Kivy's platform detection
- Special case for ARM64 Macs (checks `platform.version()`)
- Searches PATH + `/opt/homebrew/bin/` for system installations

## PyInstaller Configuration Analysis

### Key Features (spec/KaTrain.spec)
1. **Cross-platform support**: Windows, macOS, Linux
2. **Platform-specific handling**:
   - Windows: Dual builds (console/GUI), code signing
   - macOS: App bundle creation, document type associations
   - Linux: Standard executable

### macOS-Specific Build Details
1. **Dependencies**:
   - Excludes ffpyplayer and pygame to avoid SDL2 conflicts
   - Includes katago-osx binary if present

2. **App Bundle Configuration**:
   - Bundle ID: `org.katrain.KaTrain`
   - High resolution support enabled
   - SGF file type association configured
   - Icon: `katrain/img/icon.icns`

3. **Environment Variables**:
   - `KIVY_HEADLESS=1`: Prevents window creation during build
   - `KATRAIN_VERSION`: Used for app bundle version

### Data Files Included
- GUI layouts: `gui.kv`, `popups.kv`
- Configuration: `config.json`
- Resources: models/, sounds/, img/, fonts/, i18n/
- KataGo binaries and configs: KataGo/

## Platform-Specific Code Locations

### Build System
- `spec/KaTrain.spec`: Platform conditionals throughout
- `katrain/core/engine.py`: Binary path selection logic

### GUI/Runtime
- pygame dependency: macOS-only for window handling
- screeninfo dependency: Excluded on macOS

## Build Process Flow

1. **Development Install**:
   ```bash
   uv pip install -e .  # or pip3 install -e .
   ```

2. **Build Preparation**:
   - Format code: `black -l 120 .`
   - Run tests: `pytest`
   - Build translations: `python3 i18n.py`

3. **Executable Creation**:
   ```bash
   pyinstaller spec/KaTrain.spec
   ```

4. **Output**:
   - Windows: `dist/KaTrain/` (folder) and `dist/KaTrain.exe` (single file)
   - macOS: `dist/KaTrain.app` (app bundle)
   - Linux: `dist/KaTrain/` (folder)

## Metal Support Considerations

### Current State
- KataGo binary (`katago-osx`) included in bundle supports Metal
- No Metal-specific code in Python/Kivy layer
- Metal acceleration happens entirely within KataGo

### Compilation Requirements
To compile from scratch with Metal:
1. Need to build KataGo with Metal backend enabled
2. Replace bundled `katago-osx` with custom-built binary
3. No changes needed to Python/Kivy code
4. PyInstaller configuration already handles binary inclusion

## Risks and Challenges

1. **Binary Architecture**: Need to ensure KataGo binary matches system architecture (Intel vs ARM64)
2. **Code Signing**: macOS requires proper signing for distribution
3. **Dependency Conflicts**: SDL2 conflicts between pygame/ffpyplayer on macOS
4. **Metal API Version**: Need to verify minimum macOS/Metal version requirements

## Next Steps
1. Research KataGo source compilation with Metal backend
2. Set up proper build environment with all dependencies
3. Create automated build scripts for reproducible builds