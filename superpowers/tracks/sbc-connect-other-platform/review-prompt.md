# Review Request: Cross-Platform Online Play for Smart Go Board

## Context

We are building a **cross-platform online Go (Weiqi/Baduk) play feature** for a smart Go board product (RK3588 SBC + camera vision + touchscreen). The board already has:

- YOLO-based stone detection via camera (running on RK3588 NPU)
- Multi-frame move confirmation (MoveDetector, 3-frame consistency)
- Board-vision sync state machine (SyncStateMachine)
- FastAPI backend + React/TypeScript frontend
- WebSocket-based multiplayer lobby (existing, for our own platform)
- JWT auth + SQLite/PostgreSQL database
- KataGo AI engine integration for analysis

**The new feature:** Connect this smart board to external Go platforms (OGS, 野狐围棋/Fox Weiqi, 星阵围棋/Golaxy, KGS, etc.) so users can play against opponents on those platforms through their physical board.

**Product vision:** The smart board acts as a cross-platform hub — user logs into our platform first, then links third-party accounts to access each platform's online users and play games.

## What to Review

There are two artifacts to review:

### 1. Implementation Plan (`plan.md`)

A detailed technical plan covering 6 phases:

- **Phase 0:** Platform adapter infrastructure — `PlatformAdapter` ABC, data models, encrypted credential storage, `PlatformManager` orchestrator, REST API endpoints, WebSocket protocol extensions, database schema
- **Phase 1:** OGS integration — OAuth2/session auth, socket.io real-time client, REST client, coordinate translation, vision move poller integration, timer forwarding
- **Phase 2:** 野狐围棋 — Two approaches (community REST proxy vs. porting WeiqiHub's protobuf protocol)
- **Phase 3:** 星阵围棋 — Reverse-engineering REST + STOMP WebSocket from web frontend JS bundle
- **Phase 4:** KGS — JSON/HTTP polling protocol
- **Phase 5:** Frontend React components

### 2. UI Mockup (`ui-mockup.html`)

An interactive HTML mockup with 3 pages (open in browser, click tabs to switch):

- **Platform Connection Page** — Login/status cards for each platform
- **Platform Lobby Page** — Per-platform user list tabs, search, automatch, incoming challenges
- **In-Game Overlay** — Timer display (byo-yomi), opponent move indicator, platform badge, game controls

The mockup matches the existing app's dark "Zen Precision" aesthetic (Manrope + Noto Sans SC fonts, jade green #4a6b5c accent, #0f0f0f background).

## Review Dimensions

Please evaluate the following aspects and provide structured feedback:

### A. Architecture & API Design

1. Is the `PlatformAdapter` abstraction well-designed? Does it cover enough of each platform's capabilities while staying generic? Are there missing methods or over-abstractions?
2. Is the `PlatformManager` bridge between platform games and the existing KaTrain session system sound? The key design decision is: vision-detected moves submit to the remote platform first, then play locally on success. Are there edge cases or race conditions this misses?
3. Are the REST API endpoints (`/api/v1/platforms/{platform}/...`) well-structured? Would you design the URL scheme differently?
4. Are the WebSocket protocol extensions (platform_challenge, platform_game_started, etc.) sufficient for real-time UX?

### B. Platform Integration Feasibility

5. **OGS:** The plan uses socket.io + REST with two auth options (OAuth2 vs session login). Is the socket.io approach still viable given OGS is migrating to native WebSocket? Should we target the new `wss://ggs.online-go.com` protocol instead?
6. **Fox Weiqi (野狐围棋):** The plan proposes starting with the openfoxwq REST proxy then porting WeiqiHub's protobuf protocol. Is this the right sequencing? Are there better approaches?
7. **Golaxy (星阵围棋):** Reverse-engineering from the JS bundle (`app.051f010b.js`) with STOMP WebSocket. Is STOMP-over-SockJS a reasonable protocol to implement in Python? Any pitfalls?
8. **KGS:** HTTP long-polling JSON protocol (docs from 2016). Is this still functional? Should we consider alternatives?

### C. Security & Credential Management

9. The plan stores third-party credentials locally in SQLite with AES-256-GCM encryption (key derived from user password via PBKDF2). Is this appropriate for an embedded device? Are there better approaches for board-mode (no user password available — uses device-specific key)?
10. Any concerns about storing OAuth tokens, platform passwords (Fox uses MD5 hashed password), or session tokens locally?

### D. UX & Frontend Design

11. Review the UI mockup for touch-friendliness on a 1024x600 or 1280x800 embedded touchscreen. Are tap targets large enough? Is information density appropriate?
12. The lobby uses separate tabs per platform (no cross-platform user mixing). Is this the right UX choice? Or would a unified view with platform badges be better?
13. The in-game timer supports byo-yomi, fischer, canadian, and absolute time controls. Is the visual representation clear? Missing any time control systems?
14. The opponent move indicator uses a pulsing orange ring + flash animation. Is this sufficient for a physical board context where the user may be looking at the board, not the screen?

### E. Missing Concerns

15. **Reconnection & resilience:** The plan mentions auto-reconnect but doesn't detail state recovery after network drops mid-game. How should we handle: (a) our side disconnects briefly, (b) we reconnect but missed opponent moves, (c) platform marks us as timed out?
16. **Stone removal / scoring phase:** OGS has an interactive stone removal phase after two passes. The plan defers this to "screen UI only" for Phase 1. Is this acceptable? How should other platforms' endgame flows be handled?
17. **Latency:** On RK3588 over WiFi, what's the expected round-trip for vision detect → platform submit → ACK → local play → screen update? Is there a risk of the user placing the next stone before the previous one is confirmed?
18. **Testing strategy:** The plan has a manual test checklist but no automated test strategy. How would you test platform adapters without live server access (mocking, record/replay, test accounts)?
19. **Legal/TOS:** Using reverse-engineered protocols for Fox/Golaxy may violate their Terms of Service. Any recommendations for managing this risk beyond "not yet commercialized"?

### F. Anything Else

20. What am I missing? What would you add, remove, or change?

## Output Format

Please structure your review as:

```
## Summary (2-3 sentences)

## Critical Issues (must fix before implementation)
- ...

## Important Suggestions (strongly recommended)
- ...

## Minor Suggestions (nice to have)
- ...

## Questions for Clarification
- ...

## Overall Assessment
[Ready to implement / Needs revision / Major rework needed]
```
