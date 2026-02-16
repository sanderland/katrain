# UI Inventory (Refactor Baseline)

This document inventories KaTrain's current UI elements and categorizes each as:

- Reusable component: should live in `katrain/gui/components/` with clean APIs.
- App-specific view: belongs to KaTrain only (board, move tree, score graph).
- Controller/service: should coordinate app/game/config state, not be a leaf widget.

## KV Files

- `katrain/gui.kv`
  - Role: main layout, visual styles, widget rule definitions, and root `<KaTrainGui>`.
  - Pain points: very large; mixes style templates, component rules, and full-screen layout.

- `katrain/popups.kv`
  - Role: popup content layouts, especially configuration forms.
  - Pain points: heavy duplication of "label + input" rows and config section scaffolding.

## App Entry + Root

- `katrain/__main__.py`
  - `KaTrainApp.build()`
    - Loads `katrain/gui.kv`, instantiates `KaTrainGui`, then loads `katrain/popups.kv`.
  - `KaTrainGui(Screen, KaTrainBase)`
    - Category: controller + root view (should become a controller + composed layout)
    - Owns: engine lifecycle, message queue, UI-level toggles, and popup references.

## Main Screen Areas (High-Level)

- Board area
  - `BadukPanWidget` (`katrain/gui/badukpan.py`)
    - Category: app-specific view (Go board rendering)
    - Refactor intent: keep app-specific, but remove popup creation / global access from inside.
  - `BadukPanControls` (`katrain/gui/badukpan.py`)
    - Category: app-specific view/controller (board controls and engine status)

- Controls / right panel
  - `ControlsPanel` (`katrain/gui/controlspanel.py`)
    - Category: currently controller + view mixed
    - Refactor intent: split into (a) thin view widgets, (b) a controller that reacts to app state.

- Navigation / mode selection
  - `MyNavigationDrawer` (`katrain/gui/kivyutils.py`)
    - Category: reusable component candidate (drawer)
  - Mode toggles / menus defined in KV (e.g. `<PlayAnalyzeSelect>`, `<HamburgerMenuContents>`)
    - Category: should become reusable menu/list components plus a small app-specific wiring layer.

## Widgets Package (`katrain/gui/widgets/`)

- `MoveTree` (`widgets/movetree.py`)
  - Category: app-specific view
  - Current coupling: uses `App.get_running_app().gui` to mutate game state.
  - Refactor intent: expose callbacks/events like `on_select_node(node)` and handle mutations in controller.

- `ScoreGraph` (`widgets/graph.py`)
  - Category: app-specific view (Go analysis graph)
  - Current coupling: uses `App.get_running_app().gui` to navigate to nodes.
  - Refactor intent: emit navigate events; controller performs the state change.

- `I18NFileBrowser` (`widgets/filebrowser.py`)
  - Category: reusable component candidate (file picker)
  - Refactor intent: keep mostly as-is, but make it injectable/callback-driven.

- `SelectionSlider` (`widgets/selection_slider.py`)
  - Category: reusable component

- `ProgressLoader` (`widgets/progress_loader.py`)
  - Category: reusable component

## Popups (Dialogs)

All popup content is defined in `katrain/popups.kv`, and most logic lives in `katrain/gui/popups.py`.

### Config Popups (Settings)

These currently inherit from `QuickConfigGui` and rely on widget-tree-walk collection via `input_property`.

- `ConfigPopup`: engine/model/katago download/config
- `ConfigAIPopup`: AI strategy and options
- `ConfigTeacherPopup`: teaching thresholds, evaluation, theme
- `NewGamePopup`: new game setup (mode, players, komi, handicap, etc.)

Category: controller+view mixed (should become: popup view + form model + apply handler).

### File Popups

- `LoadSGFPopup`
- `SaveSGFPopup`

Category: reusable popup scaffolding + reusable file picker; app-specific behavior on submit.

### Analysis/Report/Action Popups

Removed in v2 refactor baseline (keep popups centralized in `katrain/gui/popups.py`).

### Error/Recovery

- `EngineRecoveryPopup`

Category: app-specific popup content; should use unified popup scaffolding.

## Reusable Component Candidates (Immediate)

From `katrain/gui/kivyutils.py` and popup/form patterns:

- Buttons: consolidate multiple sized/rounded/rectangle variants into a small set of canonical buttons.
- Common layouts: "card" background, section headers, standard spacing/padding.
- Form fields: text/int/float/path/select/bool fields with consistent validation and error display.
- Popup scaffolding: title, content area, standard button bar, consistent sizing.
- Drawer/menu list items.

## Key Coupling Issues to Fix

- Leaf widgets directly use `App.get_running_app().gui` and mutate game/config.
- Popups use implicit widget-tree-walk to apply config, coupling layout structure to behavior.
- Popup creation scattered across `__main__.py` and `badukpan.py` with inconsistent caching/dismiss behavior.

## Controller/Service Targets

- `PopupManager`: the only place that creates and manages Kivy `Popup` instances.
- `ConfigService`: read/write config with explicit "apply changes" semantics.
- `GameService` (or callbacks on `KaTrainGui`): navigate/select nodes, request analysis actions.

