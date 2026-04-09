# Golaxy / 星阵围棋 (19x19.com) Protocol Reference

> Researched from JS bundle analysis, sabaki-golaxy-live, and web traffic capture.

## Architecture

REST API + STOMP over SockJS for real-time events.

| Endpoint | Protocol | Notes |
|----------|----------|-------|
| `https://www.19x19.com/api/auth/*` | REST | User/auth service |
| `https://www.19x19.com/api/social/*` | REST | Social/game service |
| `https://www.19x19.com/api/engine/*` | REST | Engine/AI service |
| `wss://ws.19x19.com/api/social/channel/WS_STOMP_ENDPOINT_GOLAXY` | STOMP/SockJS | Real-time events |

## Authentication — VERIFIED 2026-04-08

**API Base:** `https://api.19x19.com` (NOT www.19x19.com!)

**Phone-only** — requires Chinese mobile number (+86). No email login.

**OAuth2 token endpoint:** `POST https://api.19x19.com/api/auth/oauth/token`

**Client credentials:**
```
Authorization: Basic Z29sYXh5X3dlYjp4aW5nemhlbjA3MzA=
(golaxy_web:xingzhen0730)
```

**SMS code request:** `GET /api/auth/sms/code?username=PHONE&login=true&area=0086`
- Note: area is `0086` not `86`

**SMS login (verified body):**
```
username=0086-{PHONE}&password=null&grant_type=sms_code&client_id=golaxy_web&sms_code={CODE}&scope=any
```
- Key differences: username has `0086-` prefix, field is `sms_code` not `code`, includes `password=null`, `client_id`, `scope=any`

**Password login:**
```
username=0086-{PHONE}&password={PWD}&grant_type=password&client_id=golaxy_web&scope=any
```

**Token refresh:**
```
grant_type=refresh_token&client_id=golaxy_web&refresh_token={TOKEN}
```

**Response:** `{access_token, refresh_token, token_type: "bearer", expires_in}`

**Authenticated requests use:** `authorization: bearer {access_token}` (lowercase "bearer")

**User identification:** `user_code` (e.g. `61707593`) — used in all social/game API paths

## REST API Services

### Game Service (`/api/social`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/gameroom/reserve` | Create game room |
| POST | `/gameroom/login/{id}` | Join room |
| POST | `/gameroom/logout/{id}` | Leave room |
| POST | `/gameroom/game/config/{id}` | Send/accept/reject game config |
| POST | `/wsgame/start/{gameId}` | Start game |
| POST | `/wsgame/genmove/{gameId}` | Place a move |
| POST | `/wsgame/backmove/{gameId}` | Request undo |
| POST | `/wsgame/action/accept/{id}` | Accept action |
| POST | `/wsgame/action/reject/{id}` | Reject action |
| POST | `/wsgame/game/end/{id}` | End game |
| POST | `/wsgame/judge/data/{id}` | Request scoring |
| GET | `/wsgame/game/meta/{id}` | Game metadata |
| GET | `/wsgame/game/state/{id}` | Game state |

### Live/Spectating (`/api/engine`) — No auth required

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/engine/golives/all` | All current live games |
| GET | `/engine/golives/history` | Historical games |
| GET | `/engine/golives/base/{liveId}?begin_move_num=0&end_move_num=N` | Live game moves |
| GET | `/engine/golives/{gameId}` | Game SGF |

## Real-Time: STOMP over SockJS

**WebSocket URL:** `wss://ws.19x19.com/api/social/channel/WS_STOMP_ENDPOINT_GOLAXY`

### Subscription channels

| Channel | Purpose |
|---------|---------|
| `/channel/gamezone/{usercode}` | Game zone events (invites, matches) |
| `/channel/wsuser/{usercode}` | User events (status, multi-device) |
| `/channel/wsgame/{gameId}` | Live game moves and state |
| `/channel/gameroom/{gameroomId}` | Room events (config, players) |
| `/channel/chatroom/{chatroomId}` | Chat messages |

### Send destinations

| Destination | Purpose |
|-------------|---------|
| `/channel/wsuser/heartbeat` | Keepalive |
| `/channel/chatroom/message/send/{id}` | Send chat |
| `/channel/chatroom/login/` | Join chat |
| `/channel/chatroom/logout/` | Leave chat |

## Implementation Strategy

1. **Start with live spectating** (no auth, proven by sabaki-golaxy-live)
2. **Add authenticated play** via REST + STOMP subscriptions
3. **Capture STOMP message payloads** from browser DevTools to document schemas

## Key Risks

- **Phone-only auth** — requires +86 number, international users excluded
- **No official API docs** — reverse-engineered from JS bundle
- **STOMP payload schemas unknown** — subscription channels known but message formats must be captured
- **Endpoints can change on any deploy** (latest JS bundle: 2026-04-03)
- **Legal gray area** — no public API terms
