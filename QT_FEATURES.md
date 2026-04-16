# Qt Feature Target

Working draft for the PySide6 KaTrain port.

This is a best-guess target spec, not a frozen contract. The aim is to preserve KaTrain's core workflows and feel while allowing substantial redesign in layout, controls, and visual language.

## Current Status

Implemented now:

- Qt is the primary KaTrain app entry point
- Kivy is no longer a runtime dependency
- Open / save SGF and open GIB / NGF
- New game flow
- Move play, pass, undo / redo, move tree navigation
- KataGo start / restart, node analysis, AI move
- Notes per node
- Right-side tabs: `Play`, `Notes`, `System`
- Compact candidate move list with selected-move details
- Ownership overlay
- Textured board, textured stones, textured last-move marker
- Textured hint overlays using KaTrain assets and point-loss colors

Implemented but still worth polishing:

- Hint sizing / alpha / label treatment
- Move tree presentation for larger games
- System tab naming / structure
- Ownership styling on top of the textured board

Not done yet:

- score graph
- teaching workflow
- mistake-jump workflow
- sound
- drag and drop / recent files / clipboard flows
- richer variation editing tools

## Product Direction

- The Qt app is the primary KaTrain application.
- Feature parity matters more than widget parity.
- Preserve KaTrain's strengths:
  - fast review of mistakes
  - strong visual board feedback
  - smooth SGF analysis workflow
  - play against AI with teaching support
  - practical engine configuration
- It is acceptable, and often preferable, to replace Kivy-era popup-heavy flows with cleaner Qt-native screens, tabs, drawers, or inline panels.

## Design Principles

- Default UI should prioritize the board and the current task.
- Secondary and diagnostic information should stay out of the default path.
- Review information should be progressive:
  - immediate board signal first
  - concise summary second
  - detailed engine internals only on demand
- Board overlays should feel like KaTrain, even if they are visually modernized.
- The old "show dots" behavior should be preserved conceptually:
  - hint severity is based on point-loss classes
  - best move and uncertain moves are visually distinct
  - overlays should be soft board-integrated marks, not random colored circles

## Core Modes

### Play

- Human vs AI
- Human vs Human
- AI vs AI
- Teaching game flow
- Quick actions:
  - play move
  - pass
  - undo/redo
  - branch navigation
  - new game
  - resign

### Review

- Load SGF and inspect move-by-move analysis
- Navigate main line and variations
- Identify mistakes quickly from the board
- Inspect candidate alternatives for the current node
- Read concise commentary for selected move
- Add personal notes to nodes

### Engine / Advanced

- Engine status
- live KataGo logs
- diagnostics and recovery
- settings and model paths
- advanced analysis actions

This does not need to be called "Engine". Alternative names worth considering:

- `System`
- `Analysis`
- `Lab`
- `Tools`
- `Diagnostics`

Current recommendation: `Analysis` for user-facing depth, or `System` if we want a cleaner split between review and internals.

## Main Window Layout

### Board Area

- Large board as the visual center of the app
- Minimal chrome around it
- Optional compact control strip near the board
- Responsive sizing for 19x19, 13x13, and 9x9

### Right Side Workspace

- Tabbed or segmented workspace is preferred over one long stacked sidebar
- Current structure:
  - `Play`
  - `Notes`
  - `System`

### Review Workspace

- Current:
  - compact overview summary
  - move tree
  - candidate move list
  - selected move details
  - fallback comment display when no candidates are shown
- Still wanted:
  - better large-tree handling
  - cleaner distinction between played move commentary and selected candidate details

### Notes Workspace

- Editable note for current node
- Clean, distraction-free text area

### Analysis/System Workspace

- Engine summary
- live log console
- recovery / restart actions
- optional advanced analysis tools

## Board Rendering

### Required

- High-quality Go board rendering
- Stones
- Last move marker
- Current-node awareness
- Good contrast on wood texture
- Smooth resizing

### Analysis Overlays

- Ownership overlay
- Candidate move overlays
- Best move emphasis
- Child move / variation indication
- Principal variation playback or stepping

### Hint Overlay Target

The old Kivy board did not use hollow colored circles as the primary language.

Target behavior:

- Use textured colored board-integrated overlays
- Severity color should follow KaTrain's point-loss classes
- Best move should be clearly but elegantly emphasized
- Low-visit / uncertain candidates should be visually quieter
- Overlay should not dominate stones or grid lines
- Numbers may be shown, but should be secondary to the shape and tint

Preferred visual direction:

- subtle textured markers with a board-colored mask underneath
- green through purple severity family
- cyan accent reserved for "best move" or active PV
- avoid hard-outline-only rings as the default

Current implementation:

- Uses the original KaTrain board and stone textures
- Uses `topmove.png`, `dot.png`, and `inner.png` in the Qt painter path
- Colors hints by point loss rather than rank
- Shows fewer hints by default
- Uses compact loss labels on stronger hints
- Keeps a cyan accent for the engine best move
- No longer uses hollow colored circles as the main visual language

### Legacy Dot Semantics To Preserve

- Color is derived from point loss, not rank
- Thresholds:
  - 12
  - 6
  - 3
  - 1.5
  - 0.5
  - 0
- Good / near-equal moves may all appear green in the opening
- Uncertain low-visit moves are reduced in confidence visually

## Candidate Move Presentation

### Default Presentation

- Keep it concise
- Table should not read like a raw KataGo dump
- Default columns should be minimal

Recommended default:

- move
- point loss

Current default:

- move
- point loss

### Details On Selection

- score
- winrate
- PV
- policy rank if available
- top move comparison

### Avoid

- Always-visible long PV columns
- dense multi-metric grids as the default
- forcing the user to parse six numbers per row before understanding the position

Current implementation already avoids this. The always-visible PV-heavy table is gone.

## Move Tree / Variation Tree

- Navigate the full game tree
- Current node must be obvious
- Main branch vs side branch distinction
- Easy selection of alternate lines
- Reasonable support for collapsing or de-emphasizing noise in large trees

Nice to have:

- branch promotion
- branch deletion
- move reordering / main-line control

## Comments And Explanations

- Show concise human-readable explanation for current move
- For selected candidate move, show:
  - move
  - point loss
  - top move if different
  - PV
  - policy context if available
- Do not flood the default panel with SGF-style verbose text
- Support a compact summary and an expanded detail view

## SGF And File Workflows

- New game
- Open SGF / GIB / NGF
- Save SGF
- Preserve notes
- Good default filename generation

Current implementation:

- New game dialog is present
- Open uses a unified game-file picker for `sgf`, `gib`, `ngf`
- Save is implemented as an explicit destination chooser
- Node notes are preserved in KaTrain SGF output

Still wanted:

- recent files
- drag and drop
- clipboard import / export
- clearer "save" vs "save as" semantics if we want both actions

Nice to have:

- recent files
- drag and drop SGF
- clipboard import/export

## Engine Integration

### Required

- Start engine
- restart engine
- stop / recover from failure
- status display
- analysis requests
- AI move generation

### Settings

- KataGo path
- model path
- human model path
- analysis config path
- visits
- time settings
- ownership toggle
- root noise

### Diagnostics

- engine state
- current query load
- recent logs
- friendly failure messages

Current implementation:

- start and restart are present
- status and friendly startup failures are present
- engine logs live in the `System` tab
- current query load is summarized in compact form

## Teaching Workflow

Target to preserve:

- analyze human move
- determine mistake severity
- optionally auto-undo poor moves
- explain what was better
- show predicted continuation

This can be redesigned substantially, but the workflow itself is important.

Current status: not implemented in the Qt app yet.

## Review Workflow

Target to preserve:

- jump through mistakes quickly
- visually identify important mistakes from the board
- compare played move with top engine alternatives
- inspect score/winrate shift
- annotate the game

Potential workflow actions:

- next mistake
- previous mistake
- next branch
- previous branch
- jump to start/end

Current status:

- generic move-tree navigation exists
- dedicated review-jump actions are not implemented yet

## AI Configuration

- Choose strategy
- Default full-strength KataGo
- HumanSL / human-style settings
- rank-based and pro-year profiles
- reasonable inline explanation of active AI profile

This does not need to be a popup. A dedicated side panel or settings section is acceptable.

## Keyboard And Mouse

Target to preserve where reasonable:

- play by click
- undo / redo
- branch navigation
- pass
- AI move
- move stepping
- home/end navigation

Qt-native shortcuts are fine as long as the common actions remain fast.

Current status: basic toolbar-driven flow exists; keyboard shortcut polish is still pending.

## Sound

- Stone placement sound
- capture sound
- optional mute toggle

Low priority compared with board/review/engine workflows.

## Performance

- Fast board redraws
- No lag on navigation through analyzed games
- Avoid blocking UI thread during engine work
- Candidate / ownership updates should feel live

## Accessibility And Readability

- Good contrast
- Reasonable font sizes
- Avoid cluttered diagnostic surfaces in default view
- Keep dense engine data behind a deliberate click/tab

## Things We Do Not Need To Match Literally

- Kivy KV layout structure
- popup architecture
- exact button placements
- exact old iconography
- exact old theme values
- one-to-one widget mapping

## Proposed Implementation Phases

### Phase 1

- stable Qt shell
- board
- SGF load/save
- move navigation
- engine start/analyze

Status: done

### Phase 2

- proper hint overlays
- compact review workspace
- notes
- cleaner move details

Status: largely done, with visual polish still ongoing

### Phase 3

- teaching workflow
- richer variation tools
- score graph
- advanced settings / diagnostics polish

Status: mostly still open

## Open Questions

- Should candidate alternatives default to top 3 or top 4?
- Should move details stay as compact inline text, or become a richer inspector card?
- Should we bring back score graph early, or keep the board-first review workflow lean until later?
