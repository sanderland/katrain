# Fox Weiqi (野狐围棋) Protocol Reference

> Researched from openfoxwq/openfoxwq_client (archived), ale64bit/WeiqiHub, and openfoxwq/api.

## Architecture

Fox uses **binary protobuf over TCP** natively. Third-party clients connect via a
**WebSocket proxy** since the native TCP protocol is not publicly documented.

| Endpoint | Protocol | Notes |
|----------|----------|-------|
| Fox native servers | TCP + protobuf | Closed-source protocol |
| `wss://api.openfoxwq.com` | WebSocket + protobuf | openfoxwq proxy (may be offline) |
| `https://foxwq-*.herokuapp.com/api/v1` | REST | Read-only API proxy |

## Connection Flow (3 stages)

1. **GetNavInfo** (`fox.proto`): Get server addresses, version info, lobby list
2. **Nav Login** (`nav.proto`): Authenticate with username + MD5(password)
3. **Frontend Session** (`fe.proto`): Main session with `FeRequest`/`FeResponse` protobuf union

## Authentication

```
LoginRequest {
  user: bytes (UTF-8 username)
  passwordHash: string (MD5 hex digest of password)
  app: string ("KaTrain-SmartBoard")
  clientVersion: Int64
  macAddress: string
}
→ LoginResponse {
  playerId: Int64
  playerInfo: PlayerInfo
  token1: bytes
  token2: bytes
}
```

## Key Protobuf Messages

### FeRequest (client → server, 24 types)

| Request | Purpose |
|---------|---------|
| `login` | Authenticate frontend session |
| `getInitData` | Initial lobby/room data |
| `getPlayerInfo` | Player profile |
| `enterRoom` / `leaveRoom` | Join/leave lobby room |
| `listRoomParticipants` | Users in room |
| `startAutomatch` / `stopAutomatch` | Automatch |
| `move` | Submit move (via `FeMoveRequest`) |
| `pass` | Pass turn |
| `resign` | Resign game |
| `requestCounting` / `countingDecision` | Scoring phase |
| `sendChallenge` / `acceptChallenge` / `cancelChallenge` | Challenge flow |
| `listGames` / `getGame` | Game history |

### FeResponse (server → client, 41 types)

| Response | Purpose |
|----------|---------|
| `enterMatchRoom` | Joined a game room |
| `matchStartEvent` | Game started |
| `nextMoveEvent` | Opponent move |
| `passEvent` | Opponent passed |
| `countdownEvent` | Clock update |
| `gameResultEvent` | Game ended |
| `countingEvent` / `countingDecision` | Scoring phase |
| `challengeEvent` / `challengeResponse` | Challenge notifications |
| `playerOnlineEvent` / `playerOfflineEvent` | User presence |
| `broadcastMoveEvent` / `broadcastStateEvent` | Spectating |

## Room Structure

- **Broadcast rooms**: Spectating (integer IDs)
- **Match rooms**: Playing (composite `MatchRoomId` with 4 integer components)
- States: `waitingForPlayers` → `playing` → `counting` → `complete`

## Ranks

`RANK_18K` through `RANK_1K`, `RANK_1D` through `RANK_10D`, `RANK_1P` through `RANK_10P`

## REST API (read-only proxy)

```
Base: https://foxwq-8e6797d8dbb9.herokuapp.com/api/v1
Headers: X-APP-ID, X-API-KEY, Authorization: Basic (MD5 password)

GET /me                    — Current user info
GET /players/{id}          — Player profile
GET /players?nick=query    — Search players
GET /players/{id}/games    — Game history
GET /top_games             — Top rated games
GET /games/{id}            — Game details (SGF)
```

## Current Status — VERIFIED 2026-04-08

**All third-party access points are OFFLINE:**
- `wss://api.openfoxwq.com` — SSL error, proxy is dead
- `foxwq-*.herokuapp.com` REST proxy — 404, shut down
- openfoxwq browser client — taken down Jan 2024
- minifox — closed-source desktop app (not usable as library)

**Fox has no Web API.** Login/play is only via official desktop/mobile apps.
The protocol is proprietary binary protobuf over TCP, and Fox has explicitly
declined to authorize third-party clients (per minifox FAQ).

## Possible Future Paths

1. **Reverse-engineer the protocol from minifox binaries** — high effort, legal risk
2. **Reconstruct .proto from archived Dart code** and build own TCP client — medium effort, ban risk
3. **Wait for official API** — Fox showed no interest (per ale64bit's outreach)
4. **Read-only via web scraping** — foxwq.com has game records pages, could scrape SGFs

## Verdict: NO-GO for live play (as of 2026-04-08)

Fox integration is not feasible without either:
- A working proxy/API (all are now offline)
- Building a full TCP protobuf client from scratch (months of work + legal/ban risk)
