## Summary

这份计划的分阶段拆分和“先 OGS 验证架构，再扩平台”的总体方向是对的，UI 方向也基本符合当前产品气质。问题在于 Phase 1 的 OGS 方案、平台对局接入现有 `/api/move` / vision 链路的方式、以及凭据与重连状态机设计还不够可靠；按现状直接开工，前期就会遇到协议失效和状态漂移问题。

## Critical Issues (must fix before implementation)

- `plan.md:266-355` 把 OGS 的 Phase 1 建在 `password grant + client_secret + socket.io` 上，这个基线风险过高。OGS 官方文档当前主推的是 OAuth2 Authorization Code + PKCE，并且官方实时协议文档已经独立成型，不应该默认把老的 socket.io/密码模式当成主路径。建议先做一个 1-2 天的 protocol spike，验证“当前可用认证方式 + 当前可用实时协议”，再冻结 OGS 适配器设计。参考：[OGS OAuth2 docs](https://docs.online-go.com/oauth2.html)、[OGS realtime protocol docs](https://docs.online-go.com/goban/modules/protocol.html)、[OGS API overview](https://docs.online-go.com/).
- `plan.md:216` 和 `plan.md:413-430` 只拦截了视觉落子，没有拦截当前代码里所有会直接改本地局面的入口。现在 `/api/move` 会立刻 `session.katrain("play", ...)`（`katrain/web/server.py:334-357`），前端 `useGameSession` 也会直接调用 `/api/move`、`/api/resign`（`katrain/web/ui/src/hooks/useGameSession.ts:109-145`）。这意味着平台对局里只要用户点屏幕落子、点“虚手”、点“认输”，本地局面就可能先于远端确认而漂移。建议改成显式的 `platform session command gateway`，统一代理 `move/pass/resign/undo/count/leave`，或者在平台对局中硬禁用所有绕过网关的本地入口。
- `plan.md:155-192` 的 `PlatformManager` 只定义了事件回调，没有定义“谁是权威状态”和“断线后如何收敛”。当前 `WebSession` 也没有 `remote_game_id / pending_action / remote_revision / snapshot` 等元数据（`katrain/web/session.py:13-27`），`_vision_move_poller` 仍然是 fire-and-forget（`katrain/web/server.py:1377-1409`）。如果出现 ACK 丢失、事件重放、短暂断网、补拉全量局面，这里没有落点。建议在 Phase 0 明确 `PlatformGameContext`：`remote_game_id`、`last_confirmed_move`、`pending_local_action`、`remote_clock_version`、`needs_resync`、`recover_from_snapshot()`，并把 reconnect/replay 写成状态机。
- `plan.md:137-153` 和 `plan.md:792-793` 的凭据方案还不够稳。对 OGS 这类支持 OAuth 的平台，不应把 `client_secret` 下发到设备；对 Fox/Golaxy 这类只能密码登录的平台，也不该把“持久化平台密码/MD5”当成常规路径。仓库里已经有设备绑定的 refresh token 存储（`katrain/web/core/credentials.py:1-110`），但它目前甚至允许在缺少 `cryptography` 时退化到弱保护；第三方平台凭据不能接受这种退化路径，必须 `fail closed`。建议重新定义威胁模型：OGS 用 public client + PKCE；Fox/Golaxy 仅在“实验性功能”里允许本地密文存储，并提供 unlink / secure erase / reauth UX。

## Important Suggestions (strongly recommended)

- `plan.md:91-132` 的 `PlatformAdapter` 过于“泛型 dict + 回调注册”，会把真正复杂度推迟到实现阶段。建议补 capability model 和强类型命令/事件：`supports_live_play`、`supports_scoring`、`supports_automatch`、`supports_rooms`，以及 `fetch_game_snapshot()`、`resync_game()`、`submit_scoring_action()`、`leave_game()`、`on_auth_expired()`、`on_reconnected()`。否则 OGS/Fox/Golaxy/KGS 的差异最后还是会回流到 `if platform == ...`。
- `plan.md:221-229` 的 WebSocket 扩展只覆盖了 lobby happy path，不足以支撑真实运行状态。建议再加 `platform_move_pending`、`platform_move_rejected`、`platform_resync_required`、`platform_auth_expired`、`platform_challenge_withdrawn`、`platform_connection_degraded`，否则前端很难把“正在提交”“需要重连”“平台已断线但本地局面还在”这些关键状态说清楚。
- `plan.md:617-739` 的前端落点和当前仓库结构不一致。现在实际入口是 `katrain/web/ui/src/kiosk/...` 和 `katrain/web/ui/src/galaxy/...`，而不是新的 `src/pages/galaxy/...`；现有大厅和对局页也已经存在（`katrain/web/ui/src/kiosk/KioskApp.tsx:37-58`、`katrain/web/ui/src/kiosk/pages/LobbyPage.tsx`、`katrain/web/ui/src/galaxy/pages/HvHLobbyPage.tsx:28-114`）。建议先决定“这是 board/kiosk 功能还是 galaxy/web 功能”，然后在现有路由与 hook 上增量扩展，避免并行造第三套大厅/对局页面。
- `plan.md:470-486` 里先做 openfoxwq 只读代理，再做 WeiqiHub 全协议，作为“Phase 2 live play” 的顺序不理想。只读代理几乎不覆盖最难的链路：登录保持、实时事件、落子 ACK、计时、重连。更好的拆法是先做一个明确的 Fox research spike，产出“是否能稳定 live play / 法律风险 / 账号风险”结论，再决定是否立项。参考：[openfoxwq client](https://github.com/openfoxwq/openfoxwq_client)、[MiniFox reverse-engineering note](https://walruswq.com/minifox).
- `plan.md:526-568` 里把 Golaxy 预设为 `STOMP + SockJS + stomp.py/aiostomp` 还太早。STOMP 本身不难，难的是 SockJS 会话建立、心跳、fallback transport，以及站点是否还保持相同 endpoint；在没有抓包证据前，不要把库和 transport 锁死。建议把 Golaxy 拆成 discovery-only 里程碑，先产出“认证方式、订阅地址、消息模型、是否真的需要 SockJS framing”的事实表。
- `plan.md:445-458` 的测试策略太弱。这个项目最怕的是协议回归和时序 bug，不是 happy path。建议至少增加三层自动化：adapter contract tests、record/replay transport fixtures、bridge state-machine tests。OGS/KGS 可以用 HTTP/WebSocket transcript fixture；Fox/Golaxy 至少要有 message parsing golden tests 和 duplicate/out-of-order event tests。
- `plan.md:801-802` 对 OGS 数子阶段的处理方向可以接受，但“只在 screen UI 处理”应该写成正式的 phase model，而不是备注。建议把 `in_game_phase` 纳入共享模型，至少覆盖 `playing / paused / scoring / finished`；否则 timer、按钮可用性、vision 绑定都会出现隐式分叉。
- KGS 不一定应该排在 Fox/Golaxy 后面固定做。官方 JSON/JSP 协议文档现在仍然公开可访问，虽然老、虽然长轮询，但它至少是 documented path。建议把“KGS 作为第二个 live-play adapter 还是 Fox 作为第二个 market-priority adapter”单独拿出来评估，而不是在计划里写死顺序。参考：[KGS protocol docs](http://www.gokgs.com/help/protocol.html).
- `plan.md:198-214` 的 REST URL 能用，但会很快膨胀成动作型 API。更稳的方式是提前资源化，例如 `/platform-connections/{platform}`、`/platforms/{platform}/challenges/{id}/accept`、`/platform-games/{session_id}/actions/pass`，否则一旦加入 challenge id、automatch ticket、connection state，URL 会变得越来越碎。

## Minor Suggestions (nice to have)

- `ui-mockup.html:614`, `ui-mockup.html:732`, `ui-mockup.html:844` 用了固定 `320px sidebar + 520px board + 340px info panel`，而文件里没有任何 `@media` / small-height 规则；在 1024x600 触摸屏上会非常紧。建议补一个 compact layout：大厅侧边栏折叠成底部 sheet，对局页右侧信息栏在小屏下改为顶部或底部卡片。
- `ui-mockup.html:71-82`, `ui-mockup.html:591-605`, `ui-mockup.html:677-687` 的按钮和行高整体偏小，很多交互落在 32-36px 级别，离“站着操作、快速点按”的触摸目标还有距离。建议把主要点击目标统一拉到 44-48px。
- Separate tabs per platform are the right MVP choice. 排名体系、在线状态、房间结构、可挑战条件都不一致，先不要做统一混排列表；只需要在顶层连接页做跨平台概览即可。
- `ui-mockup.html:774-803` 的对手落子提示只靠橙色环和 flash，不足以覆盖“用户正在低头看实体棋盘”的场景。建议加一条更强的 secondary cue：短促音效、顶部 banner，以及“上一步坐标”文本。
- `plan.md:646-660` 的计时器组件应明确 Canadian 的“本轮剩余手数”显示方式，以及平台原生显示文案的保留策略；否则不同平台计时体系会被过度归一化。
- 如果产品最终要面向商业发布，Fox/Golaxy 这两块需要从 day 0 就挂 feature flag、实验性文案和 server-side kill switch，不能等到上线前再补。

## Questions for Clarification

- 这个功能首发目标到底是“board/kiosk only”还是“桌面/web 也要支持”？这会直接决定 OGS PKCE 流程、账号 linking UX 和前端落点。
- 平台对局里是否允许屏幕直接落子，还是强制只能通过视觉检测落子？这决定 server command gateway 的范围和 UI 约束。
- Fox / Golaxy 是实验性功能、内测功能，还是商业正式功能？如果是后者，法律/TOS 评审应该成为 Phase 0 的 exit criteria。
- 第三方账号的绑定主体是什么：KaTrain 云端用户、设备本地用户，还是“某个设备上的当前登录用户”？当前计划在 board mode 和 user-linked storage 之间还有点混。

## Overall Assessment

Needs revision
