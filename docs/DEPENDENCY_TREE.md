# KaTrain Dependency Tree

## Python Dependencies Hierarchy

### Core Application Dependencies
```
KaTrain
├── kivy>=2.3.1                  # Core GUI framework
│   ├── SDL2                     # Window/graphics backend
│   ├── OpenGL                   # Graphics rendering
│   └── Cython                   # Performance extensions
├── kivymd==0.104.1              # Material Design UI components
│   └── kivy (peer dependency)
├── pygame~=2.0 (macOS only)     # Window handling on macOS
│   └── SDL2                     # Shared with Kivy
├── screeninfo>=0.8.1 (non-macOS) # Screen detection
├── chardet>=5.2.0               # Character encoding detection
├── docutils>=0.21.2             # Documentation processing
├── ffpyplayer>=4.5.1            # Audio/video playback
│   └── FFmpeg libraries
└── urllib3>=2.2.2               # HTTP client library
```

### Development Dependencies
```
Development Tools
├── black>=24.8.0                # Code formatter
├── polib>=1.2.0                 # i18n/translation tools
├── pytest>=8.3.2                # Testing framework
│   ├── pluggy
│   └── pytest plugins
├── pyinstaller>=6.14.1          # Executable builder
│   ├── altgraph                 # Dependency graph
│   ├── macholib (macOS)         # Mach-O binary handling
│   └── pefile (Windows)         # PE binary handling
└── tomli>=1.2.0 (Python<3.11)   # TOML parser
```

### System Dependencies

#### macOS
- Xcode Command Line Tools (for compilation)
- Python 3.9-3.13
- SDL2 (via pygame/Kivy)
- OpenGL support (built-in)
- Metal framework (for KataGo, built-in)

#### KataGo Binary Dependencies
- C++ runtime libraries
- OpenCL/CUDA/Metal drivers (platform-specific)
- zlib compression library
- OpenSSL (for network features)

## Platform-Specific Dependency Notes

### macOS Specifics
1. **pygame**: Required for proper window handling
2. **ffpyplayer**: Excluded in PyInstaller to avoid SDL2 conflicts
3. **Metal Support**: Provided by system, no additional dependencies

### Dependency Conflicts
1. **SDL2 Duplication**: Both Kivy and pygame use SDL2
   - Resolved by excluding ffpyplayer on macOS
2. **Binary Architecture**: Must match system (x86_64 vs arm64)

## Version Constraints
- Python: >=3.9, <3.14
- Kivy: >=2.3.1 (no upper bound)
- KivyMD: ==0.104.1 (pinned version)
- All other deps use compatible version specifiers (~= or >=)

## Hidden Dependencies
These are discovered at runtime or build time:
1. **Kivy providers**: Audio, video, window providers selected at runtime
2. **Platform libraries**: 
   - macOS: CoreAudio, CoreVideo, Metal
   - Windows: DirectX, Windows Media
   - Linux: ALSA, PulseAudio, X11/Wayland

## KataGo Integration Points
1. **Subprocess Communication**: No Python dependencies
2. **Binary Location**: Hardcoded paths in engine.py
3. **Configuration**: JSON files in KataGo directory
4. **Models**: Neural network files in models/

## Build-Time Dependencies
1. **Hatchling**: Modern Python build backend
2. **UV**: Fast Python package manager (optional)
3. **PyInstaller Hooks**: Custom hooks for Kivy/KivyMD

## Dependency Installation Order
1. System dependencies (Xcode, Python)
2. Core Python packages (pip, setuptools)
3. Application dependencies (via pyproject.toml)
4. KataGo binary (pre-compiled or built separately)