# Review Evaluation: Codex vs Gemini

## Overall Assessment of Reviews

**Codex** — 更深入、更有架构洞察力。识别出了 3 个真正的架构缺陷（command gateway、状态机、capability model），这些问题如果不修复，实现阶段会遇到严重困难。"Needs revision" 的判断是合理的。

**Gemini** — 更务实、更面向落地。建议简洁可操作，但深度不够。"Ready to implement with minor adjustments" 过于乐观——Codex 发现的 command gateway 问题确实是 critical 级别的。

---

## 逐条评估

### 两者一致的建议（强信号，全部采纳）

| 建议 | Codex | Gemini | 决策 |
|------|-------|--------|------|
| OGS 不应建在 socket.io 上，应直接用原生 WebSocket | Critical | Critical | **采纳** — 做 protocol spike 验证后锁定 |
| 视觉落子→平台ACK 之间需要"确认中"状态反馈 | Critical | Critical | **采纳** — 加 pending state + UI lock |
| 触摸目标太小（< 44px） | Minor | Important | **采纳** — UI mockup 后续调整 |
| 自动化测试策略缺失 | Important | Important | **采纳** — 加 adapter contract tests + record/replay |
| 断线重连需要显式状态恢复 | Important | Important | **采纳** — 纳入 PlatformGameContext |
| 对手落子需要音效提示 | Minor | Minor | **采纳** — 低成本高价值 |
| 独立平台 tab 是正确的 UX 选择 | Minor (agree) | Minor (agree) | **保持不变** |

### Codex 独有的深度建议

| 建议 | 评估 | 决策 |
|------|------|------|
| **Command gateway**: 平台对局必须拦截所有入口（屏幕落子/虚手/认输），不只是视觉落子 | **完全正确**。这是最重要的架构遗漏。当前 `/api/move` 直接 `katrain.play()`，平台对局中屏幕点击会导致本地状态与远端不一致。 | **采纳** — Phase 0 加 PlatformCommandGateway |
| **PlatformGameContext 状态机**: remote_game_id, last_confirmed_move, pending_local_action, needs_resync | **正确**。没有这些元数据，断线重连和 ACK 丢失无法处理。 | **采纳** — Phase 0 补充 |
| **Capability model**: supports_live_play, supports_scoring, supports_automatch 等 | **合理**。避免 `if platform == ...` 扩散。但 MVP 阶段平台少，不需要过度抽象。 | **部分采纳** — 加基础 capability 声明，不做复杂的 feature negotiation |
| **WebSocket 错误事件**: platform_move_rejected, platform_resync_required, platform_auth_expired | **正确**。只有 happy path 事件不够，前端需要知道异常状态。 | **采纳** — 补充 error/degraded 事件 |
| **前端落点**: kiosk vs galaxy 混乱 | **有道理**。但这个决策取决于产品定位，不是架构问题。 | **记录为 open question** — 需要用户决定 |
| **Fox research spike**: 先验证可行性再立项 | **务实**。比"先做只读代理再做全协议"更好。 | **采纳** — Phase 2 改为 spike-first |
| **Golaxy discovery milestone**: 不要过早锁定 STOMP | **正确**。还没抓包就确定技术栈太早。 | **采纳** — Phase 3 改为 discovery-first |
| **REST URL 资源化** | 合理但非必要。当前 URL 结构对 MVP 够用。 | **暂不采纳** — MVP 后重构 |
| **Game phase model**: playing/paused/scoring/finished | **正确**。OGS 有 stone removal，其他平台有不同的终局流程。 | **采纳** — 加到共享模型 |
| **KGS 排序**: 不应写死在 Fox/Golaxy 后面 | 理解但不同意。用户明确说中国市场优先。KGS 技术简单但用户价值低。 | **不采纳** — 维持用户决定的优先级 |
| **凭据 fail closed**: 不允许退化到弱保护 | **正确**，但力度可以适当放宽。产品尚未商业化。 | **部分采纳** — 第三方凭据强制加密，但不需要 PKCE 等完整 OAuth 安全审计 |
| **Feature flag for Fox/Golaxy** | 商业化前不需要 server-side kill switch。 | **暂不采纳** |

### Gemini 独有的建议

| 建议 | 评估 | 决策 |
|------|------|------|
| **Credential refresh callback**: adapter 刷新 token 后要通知 manager 更新存储 | **好 catch**。Codex 没提但确实需要。 | **采纳** — 加 on_token_refreshed callback |
| **Hardware-bound encryption**: 用 CPU 序列号派生密钥 | **实用**。RK3588 有唯一 serial number。 | **采纳** — board mode 用硬件绑定密钥 |
| **Chat support** | Nice to have，Phase 1 不需要。 | **暂不采纳** — 后续加 |
| **Guest accounts** | OGS 支持，但产品需要用户有自己的账号。 | **暂不采纳** |
| **Ruleset in PlatformGameSession** | **正确**。当前模型缺少 rules 字段。 | **采纳** — 加 rules 字段 |

### Codex 提出的澄清问题

| 问题 | 回答 |
|------|------|
| board/kiosk only 还是桌面/web 也支持？ | **Board/kiosk first**。Web 版后续可以复用后端但 UI 不同。 |
| 平台对局是否允许屏幕直接落子？ | **允许**。物理棋盘 + 屏幕都是输入方式，都需要走 command gateway。 |
| Fox/Golaxy 是实验性还是商业功能？ | **实验性**。不需要法律审计作为 Phase 0 exit criteria。 |
| 账号绑定主体？ | **设备上的当前登录用户**。board mode 下一个用户绑定多个平台。 |

---

## 对计划的修改清单

### Phase 0 修改
1. **新增 PlatformCommandGateway** — 拦截所有游戏操作入口（move/pass/resign/undo/count），平台对局中统一走远端确认流程
2. **新增 PlatformGameContext** — 包含 remote_game_id, last_confirmed_move, pending_action, remote_clock_version, needs_resync, game_phase
3. **PlatformAdapter 加 capability 声明** — supports_live_play, supports_scoring, supports_automatch, supports_rooms
4. **PlatformAdapter 加状态回调** — on_token_refreshed, on_reconnected, on_auth_expired
5. **WebSocket 补充异常事件** — platform_move_pending, platform_move_rejected, platform_resync_required, platform_auth_expired
6. **共享模型加 GamePhase** — playing, paused, scoring, finished
7. **PlatformGameSession 加 rules 字段**
8. **凭据方案**: 第三方凭据强制加密，board mode 用硬件序列号派生密钥

### Phase 1 修改
1. **OGS protocol spike first** — 1-2 天验证当前可用的认证方式 + 实时协议，再锁定适配器设计
2. **优先尝试原生 WebSocket** (`wss://ggs.online-go.com`)，socket.io 作为 fallback
3. **落子确认 UX** — 视觉/屏幕落子后立即显示"确认中"状态，锁定输入直到 ACK

### Phase 2 修改
1. **改为 spike-first** — 先做 1-2 天 research spike 验证 live play 可行性，再决定是否立项
2. 删除"先做只读代理再做全协议"的分步策略

### Phase 3 修改
1. **改为 discovery-first** — 先抓包分析实际协议，不预设 STOMP，产出事实表后再决定技术栈

### Phase 5 (Frontend) 修改
1. **触摸目标**: 主要交互元素 ≥ 44px
2. **对手落子音效**: 加音效提示
3. **前端落点**: 标注为 open question（kiosk vs galaxy），待用户决定
