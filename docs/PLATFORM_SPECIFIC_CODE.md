# Platform-Specific Code Inventory

## Files with Platform-Specific Logic

### 1. katrain/core/engine.py
**Purpose**: KataGo binary path selection
```python
# Lines 66-73: Platform-specific binary selection
if kivy_platform == "win":
    exe = "katrain/KataGo/katago.exe"
elif kivy_platform == "linux":
    exe = "katrain/KataGo/katago"
else:
    exe = find_package_resource("katrain/KataGo/katago-osx")  # macOS
    if not os.path.isfile(exe) or "arm64" in platform.version().lower():
        exe = "katago"  # Fallback to system katago
```

**macOS Specifics**:
- Looks for `katago-osx` binary (currently missing in repo)
- Special handling for ARM64 Macs
- Falls back to system-installed katago
- Checks `/opt/homebrew/bin/` for Homebrew installations

### 2. katrain/__main__.py
**Purpose**: Application entry point with platform setup
- May contain platform-specific initialization
- Window management setup

### 3. katrain/gui/sound.py
**Purpose**: Audio playback implementation
- Platform-specific audio providers
- May use different backends on macOS vs others

### 4. katrain/gui/popups.py
**Purpose**: Dialog and popup implementations
- Platform-specific file dialogs
- Native OS integration for file selection

### 5. katrain/gui/widgets/filebrowser.py
**Purpose**: File browser widget
- Platform-specific path handling
- OS-specific file system navigation

### 6. spec/KaTrain.spec (PyInstaller)
**Platform Detection**:
```python
is_windows = sys.platform.startswith('win')
is_macos = sys.platform == 'darwin'
is_linux = sys.platform.startswith('linux')
```

**macOS-Specific Build Configuration**:
- Excludes ffpyplayer and pygame to avoid conflicts
- Creates .app bundle with proper metadata
- Handles code signing and notarization
- SGF file type associations

### 7. pyproject.toml
**Platform-Specific Dependencies**:
```toml
"pygame~=2.0 ; platform_system == 'Darwin'"
"screeninfo>=0.8.1,<0.9 ; platform_system != 'Darwin'"
```

## Platform-Specific Features

### macOS
1. **Window Management**: Uses pygame for proper window handling
2. **App Bundle**: Full .app creation with icon and file associations
3. **Metal Support**: Through KataGo binary (no Python-level code)
4. **Homebrew Integration**: Searches Homebrew paths for katago

### Missing macOS Binary
**Important**: The repository lacks `katago-osx` binary that the code expects. The included `katago` file is a Linux ELF binary, not macOS.

## Build System Platform Handling

### PyInstaller Spec
1. **Data Files**: Same across platforms
2. **Binaries**: Platform-specific inclusion
3. **Hidden Imports**: Windows-specific modules
4. **Excludes**: macOS-specific exclusions

### Environment Variables (Build Time)
- `KIVY_HEADLESS=1`: Prevents window creation
- `KIVY_NO_WINDOW=1`: Disables window system
- `KIVY_GL_BACKEND=mock`: Uses mock OpenGL

## Recommendations for Metal Compilation

1. **KataGo Binary**: Need to compile KataGo with Metal backend
2. **Binary Placement**: Place as `katrain/KataGo/katago-osx`
3. **Architecture Detection**: Enhance ARM64 detection logic
4. **Path Handling**: Consider universal binary support

## Testing Requirements

### Platform-Specific Tests Needed
1. Binary detection and loading
2. Window management on macOS
3. File dialog operations
4. App bundle functionality
5. Metal acceleration verification