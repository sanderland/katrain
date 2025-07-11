# Phase 1 Issues to Create

Copy and paste these into GitHub Issues:

## Issue 1: Analyze current build system and dependencies

**Title**: [RESEARCH] Analyze current build system and dependencies

**Body**:
### Research Question
We need a complete understanding of KaTrain's build system, dependencies, and platform-specific requirements to plan our macOS Metal compilation strategy.

### Background
Before we can compile KaTrain from scratch with Metal support, we need to map out all components and their interdependencies.

### Scope
- Python dependencies and versions
- KataGo binary integration points
- PyInstaller configuration analysis
- Platform-specific code identification
- Build script examination

### Research Tasks
- [ ] Analyze `pyproject.toml` and document all dependencies
- [ ] Map KataGo binary loading in `katrain/core/engine.py`
- [ ] Document PyInstaller spec files in `spec/`
- [ ] Identify all platform-specific code blocks
- [ ] Review existing build documentation
- [ ] Check for hidden dependencies or assumptions

### Success Criteria
Complete dependency tree documented with version requirements and platform-specific notes.

### Deliverables
- [ ] Dependency analysis document
- [ ] Build system architecture diagram
- [ ] Platform-specific code inventory
- [ ] Risk assessment for Metal compilation

**Labels**: phase-1-analysis, research, build-system

---

## Issue 2: Investigate KataGo Metal support

**Title**: [RESEARCH] Investigate KataGo Metal support requirements

**Body**:
### Research Question
How is Metal support currently implemented in KataGo, and what are the requirements for compiling it from source?

### Background
The bundled KataGo binaries support Metal, but we need to understand how to compile this ourselves.

### Scope
- KataGo source code Metal backend
- Compilation flags and requirements
- Performance characteristics
- Metal API usage

### Research Tasks
- [ ] Clone KataGo repository and examine Metal backend code
- [ ] Document Metal-specific compilation flags
- [ ] Identify minimum macOS/Metal versions required
- [ ] Research Metal performance optimization options
- [ ] Compare bundled binary capabilities with source options
- [ ] Test Metal detection and fallback mechanisms

### Success Criteria
Clear understanding of how to compile KataGo with optimal Metal support.

### Deliverables
- [ ] KataGo Metal compilation guide
- [ ] Performance benchmark plan
- [ ] Metal compatibility matrix
- [ ] Compilation flag recommendations

### Resources
- https://github.com/lightvector/KataGo
- KataGo compilation documentation
- Apple Metal documentation

**Labels**: phase-1-analysis, research, metal-support

---

## Issue 3: Create comprehensive build documentation

**Title**: [DOCS] Create comprehensive build documentation for macOS Metal

**Body**:
### Documentation Type
- [x] Build Instructions
- [x] Architecture Documentation
- [x] Setup/Installation Guide

### What needs to be documented?
Complete guide for building KaTrain from source with Metal support on macOS.

### Target Audience
Developers who want to compile KaTrain with custom modifications or optimizations.

### Current State
- INSTALL.md exists but focuses on installation from releases
- No detailed compilation guide for Metal support
- Build prerequisites not fully documented

### Proposed Content Outline
1. Prerequisites
   - System requirements
   - Software dependencies
   - Development tools
2. Environment Setup
   - Python environment
   - C++ build tools
   - Metal SDK verification
3. Step-by-Step Build Process
   - Cloning repositories
   - Dependency installation
   - KataGo compilation
   - KaTrain build process
4. Troubleshooting
   - Common errors
   - Debug techniques
   - Performance validation
5. Optimization Guide
   - Compiler flags
   - Metal optimizations
   - Build size reduction

### Location
`docs/BUILD_MACOS_METAL.md`

### Related Issues/PRs
- Depends on Issue #1 (build system analysis)
- Depends on Issue #2 (KataGo Metal research)

**Labels**: phase-1-analysis, documentation