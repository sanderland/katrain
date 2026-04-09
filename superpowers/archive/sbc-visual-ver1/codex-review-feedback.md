# Codex Review Feedback: SBC Visual Recognition Integration Plan v1

## 总体判断

这份计划的方向基本正确：它抓住了 3 个真正困难的问题，分别是轻量推理后端、物理棋盘与数字棋盘同步、以及 Kiosk UI 的校准/提示流。但它还**不适合直接进入实现**。主要原因不是“任务太大”，而是计划里有几处关键假设和当前代码基线不一致，并且对 RK3562 的资源预算、同步状态机、以及前后端边界定义还不够严格。

如果现在按 v1 直接做，大概率会在中后期卡在下面几类问题上：

1. 内存/CPU 预算不成立，导致 SBC 上整机不稳定。
2. 同步逻辑重复且相互打架，产生大量误报。
3. 某些页面并没有 Claude 计划假设的 session/back-end 形态，接不进去。
4. “重新同步”这类功能没有定义对 KaTrain game tree 的语义，最后只能做成 UI 假同步。

我的结论是：**保留目标，重写实施顺序和架构边界，再开始编码。**

---

## 这份计划做得对的地方

- 明确保留现有 `katrain/vision/` 管线，而不是推倒重做。
- 看到了 `ultralytics` 在 SBC 上的主要问题不是“慢”，而是“常驻内存太贵”。
- 识别了校准页、对局同步、死活题摆盘引导、研究模式重同步这些确实要单独设计。
- 有测试意识，知道不能只做 happy path。

这些判断都对，所以这不是“方向错了”，而是“实施计划还不够工程化”。

---

## 关键问题

### 1. 单进程架构对 2GB SBC 风险过高

v1 把 `VisionService`、OpenCV、推理后端、MJPEG 编码、FastAPI、WebSocket、KaTrain session、Chromium kiosk 都默认放进同一个 Python 进程生态里。这在 MacBook 上可以，在 RK3562 上风险很高。

主要问题：

- 一旦推理端或 `cv2.VideoCapture` 状态异常，容易把整个 board mode 服务一起拖死。
- 内存峰值不可控，尤其是模型加载、JPEG 编码、Chromium 同时工作时。
- 线程共享对象太多，排查“卡顿、假死、偶发崩溃”会很痛苦。

建议：

- SBC 上的视觉模块默认做成**独立 worker 进程**，FastAPI 只是控制面。
- 进程之间用轻量 IPC 传递：
  - 最新状态
  - 最新观测棋盘
  - 最新预览 JPEG
  - 控制命令（绑定 session、设置 expected board、确认校准、重置）
- 开发机可以保留 in-process 适配层，但 SBC 不建议。

### 2. 计划与当前代码基线有多处不一致

这不是小问题，会直接导致任务拆分失真。

#### 2.1 `GameState.stones` 结构假设错了

计划里写的是对象数组 `[{color, coords}]`，但实际前后端现在用的是 tuple 结构：

- `katrain/web/interface.py`
- `katrain/web/ui/src/api.ts`

实际类型是：

```ts
[player, coords, aiScore, aiWinrate][]
```

同步引擎如果按错误结构设计，后面所有 `expected_board` 转换逻辑都要返工。

#### 2.2 `TsumegoProblemPage` 不是 session 驱动页面

当前死活题页面走的是：

- `katrain/web/ui/src/kiosk/pages/TsumegoProblemPage.tsx`
- `katrain/web/ui/src/hooks/useTsumegoProblem.ts`

这是**前端本地状态机**，不是 `WebSession`/`session.katrain("play")` 驱动。所以 v1 里“bind session + setup mode + play mode”的设计不能直接套进去。

这意味着死活题集成需要二选一：

1. 先把 tsumego 改造成后端 session 驱动。
2. 保持当前前端逻辑，但让视觉服务支持“前端下发 expected board”模式。

对当前阶段而言，我更推荐第 2 种，改动小得多。

#### 2.3 `ResearchPage` 不是“研究中的棋盘页”

当前 `katrain/web/ui/src/kiosk/pages/ResearchPage.tsx` 只是研究模式入口/建局页。它会 `navigate('/kiosk/research/session/${sessionId}')`，但 `katrain/web/ui/src/kiosk/KioskApp.tsx` 里目前并没有对应 route。

也就是说，v1 把研究模式视觉集成挂在 `ResearchPage` 上，本身就是挂错位置了。这里应该先明确：

- 真实的研究对局页在哪
- 如果还没有，就要先补这个页，再谈 vision integration

#### 2.4 `GamePage` 不在 `KioskLayout` 里

`GamePage` 路由是 fullscreen route，不走 `KioskLayout`，也就没有共享 `StatusBar`。所以 v1 里“StatusBar 上显示所有核心视觉状态”只覆盖了标准页，覆盖不到实际最关键的对局页。

这意味着视觉状态提示至少要分两层：

- 标准页：`StatusBar`
- fullscreen 对局页：独立浮层/状态条

#### 2.5 现有 `VisionPlayerBridge` 被计划忽略了

`katrain/vision/katrain_integration.py` 已经有 `VisionPlayerBridge.submit_move()`。虽然它目前还不够完整，但它说明仓库已经有“视觉落子桥”的概念。v1 另起一套 “VisionService -> POST /api/move” 其实是在绕开现有边界。

更合理的方向是复用/扩展这个桥，而不是让服务自己 HTTP 调自己。

### 3. `MoveDetector` 和 `BoardSyncEngine` 的职责重叠

当前管线已经有：

- `MotionFilter`
- `MoveDetector` 的 3 帧一致性确认

v1 又引入一个“全盘比较”的 `BoardSyncEngine`，但没有严格定义：

- 谁来确认“这是一手新棋”
- 谁来处理捕获后的暂态
- 谁来抑制检测抖动
- 谁来负责 reset / force sync

如果这个边界不清楚，最典型的坏结果是：

- `MoveDetector` 说“有新子”
- `BoardSyncEngine` 同时说“整盘不匹配，非法变更”
- 前端在合法落子时弹非法提示

建议重构为三层而不是两层：

1. `ObservedBoard`
   - 来自视觉管线
   - 包含稳定性、歧义、置信度、最后确认新增点
2. `ExpectedBoard`
   - 来自 session 或前端问题状态
3. `SyncStateMachine`
   - 只负责比较 `ObservedBoard` vs `ExpectedBoard`
   - 不重复做新落子确认

也就是说：

- “新增一手棋”的确认仍应主要依赖现有 `MoveDetector`
- “整盘一致/待提子/异常变化/摆盘进度”由新的状态机负责

### 4. `VisionService` 通过 HTTP 调自己提子是不合适的

v1 里的“检测到新棋后 `POST /api/move`”是实现层面的大坑。

问题：

- 同进程自调 HTTP 没必要，增加延迟和错误面。
- 它把领域动作伪装成 REST 调用，丢掉了类型和事务边界。
- `session.lock` 已经广泛存在于 `katrain/web/server.py`，你最终还是得回到 session 层。

建议：

- 视觉侧只发**命令**，不要发 HTTP。
- 由 app 主循环或 session adapter 执行：
  - `play move`
  - `set expected board`
  - `accept resync`
- 这些命令统一走 session/domain 层，锁和广播也在这一层收敛。

### 5. 推理后端计划还缺少“导出契约”

v1 里最大的不确定点，不是“要不要自己写 NMS”，而是**导出后的 ONNX/RKNN 输出到底长什么样**。把输出形状写死成 `(1, 6, 8400)` 太脆弱了。

这里需要一个明确的 artifact contract：

- 输入尺寸
- 通道顺序
- normalize 规则
- 输出 tensor 名称/形状
- 是否已包含 NMS
- 类别顺序
- bbox 解码公式

建议：

- `export_onnx.py` 在导出模型时，同时导出 `model.meta.json`
- `OnnxBackend` / `RknnBackend` 读这个 sidecar，而不是猜
- 把“某个实际导出的 ONNX 文件 + 预期输出”纳入测试夹具

### 6. 模型策略没有先做 feasibility gate

仓库里的 `katrain/vision/README.md` 已经给了一个很重要的信号：

- `yolo11n` 真实图像表现很差
- `yolo11x` 实际泛化更好，但权重大、推理重

所以这件事不能在计划里默认成“上 ONNX/RKNN 就行了”。应该先做一个明确的前置闸门：

- `n/s/m/x` 哪个模型在 RK3562 上才是真正可用的
- ONNX CPU 跑得动吗
- RKNN 真能编过、跑通、准确率还能接受吗

我的建议是：

- **先把 ONNX 作为主路径**
- RKNN 作为实验路径，只有在真实板子上跑通并达到指标后才升级为正式选项
- 模型优先评估 `m` 或裁剪后的 `s/m`，不要一开始在计划里默认 `x`

### 7. 30fps MJPEG 目标不现实

这不是 UI 优化问题，而是系统资源问题。对 4x Cortex-A55 来说：

- 摄像头采集
- OpenCV 预处理
- 模型推理
- JPEG 编码
- WebSocket/HTTP

同时跑时，30fps MJPEG 非常浪费。

实际需求也不需要 30fps。棋子摆放是人类尺度动作，不是高速场景。

建议把 3 个频率分开：

- capture: 8-10 fps
- inference: 2-5 fps，且仅在画面稳定后推进
- preview stream: 2-3 fps

并加上背压策略：

- 只保留最新帧
- 编码慢就丢旧帧
- 没有 viewer 时不要持续 JPEG 编码

### 8. “校准”混淆了两个概念

v1 里把这些东西混在了一起：

- 相机内参 calibration
- 本次开机的棋盘位姿/透视锁定

这两个生命周期不一样：

- 相机内参通常可以长期持久化
- 棋盘位置锁定才是 per-boot / per-session

建议拆开命名：

- `camera_intrinsics`
- `board_pose_lock`

否则后面会出现“确认校准”到底是在确认哪件事的歧义。

### 9. `重新同步` 没有定义对 game tree 的语义

这是研究模式里最危险的一个设计空洞。

如果用户点“重新同步”，系统到底做什么？

- 直接把 expected board 改成当前物理棋盘？
- 在 KaTrain 里插入一串手数？
- 生成 setup node / AE-AB-AW？
- 新开一个 variation 分支？

如果只改前端或 vision service 的 expected board，而不改 KaTrain 内部状态，那就是假同步，后续分析、导航、保存 SGF 都会出问题。

建议明确成一种可落地语义，例如：

- 研究模式的 resync 只允许生成一个新的 setup node/variation
- 成功后 KaTrain state、前端 board、vision expected board 三者同时更新

在这件事没有定义清楚前，不应该把 “重新同步” 当作一个普通按钮任务。

### 10. 测试计划不够贴近真实风险

v1 列了很多测试文件名，但还缺 3 类真正关键的验证：

1. **回放测试**
   - 用录制的帧序列重放真实场景
   - 包括手遮挡、提子延迟、光照变化、棋盘晃动
2. **契约测试**
   - 固定 ONNX artifact 的输入输出
   - 防止导出参数变化后后处理 silently break
3. **板端 soak test**
   - 长时间运行监控 RSS、CPU、重连、相机热插拔

没有这三类测试，CI 绿了也不说明板子上真的稳定。

---

## 对 review-prompt 中关键问题的直接回答

### Memory & Performance

- ONNX Runtime 在 2GB 机器上不是天然安全，尤其如果继续沿用大模型和高分辨率输入。
- 30fps MJPEG 不应作为目标，建议降到 2-3fps 预览。
- 处理 loop 必须限速，视觉同步本质上不需要高帧率。
- SBC 上更推荐独立 worker 进程而不是线程。

### Inference Backend

- 不应硬编码 YOLO ONNX 输出 shape。
- 后处理逻辑必须绑定导出契约和实际 artifact 测试。
- RKNN 应视为“需要实机验证的候选项”，不能在计划阶段默认成立。
- `ncnn` 可以作为后备选项，但不建议在当前阶段再引入第三条后端线，先把 ONNX 主路径做稳。

### Sync Engine

- 必须定义抖动抑制和状态滞后，否则误报会很多。
- `MoveDetector` 与新同步引擎必须职责分离，不能双重判断新棋。
- 提子提示应是 sticky state，不是一次性 event。
- tsumego 摆盘应允许任意顺序；错色/错位要显式提示。
- research resync 必须落到真实 game tree 语义。

### Architecture

- 不建议同进程自发 HTTP 调 `/api/move`。
- `bind_session(session_id)` 只在“设备单活 session”语义成立时才合理，必须禁止并发控制权冲突。
- 长连接视频流要做 viewer-aware 编码，不要持续空转。

### Frontend

- `<img>` MJPEG 可以保留，但必须有断流/相机断开 fallback UI。
- 800x480 上不适合过多 modal，大部分状态应用非阻塞提示，只有“不能继续下”的情况才 modal。
- tsumego 更适合“全屏相机 + 小棋盘参考”的 setup wizard，而不是一上来 split view。
- session-bound 页面优先复用已有 game websocket，setup/calibration 页面再单独使用 vision channel。

### Edge Cases

- 相机中途断开应退回 touch-only，而不是把整局锁死。
- 棋盘整体被碰动时，不应逐点报非法；应该进入“board lost / re-acquire”状态。
- 光照恶化应进入 degraded mode，而不是继续自信地产出错误同步。
- 显示旋转和物理棋盘坐标应解耦，vision 只关心物理坐标系。

### Testing

- CI 里至少要有 ONNX replay/contract tests。
- 需要录制真实对局短视频作为 golden replay 数据。
- 全链路测试要支持 fake camera / frame replay，不要依赖真摄像头。

---

## 建议的改进版实施计划

### Phase 0: Feasibility Gate

先做 3 个最小验证，再决定后续实现路线。

1. 在开发机导出 2-3 个候选模型及 sidecar metadata。
2. 在 RK3562 上实测：
   - 冷启动时间
   - 常驻 RSS
   - 单帧延迟
   - 真实棋盘准确率
3. 验证 RKNN 工具链是否真的可用。

通过条件：

- ONNX 主路径可运行且总内存预算可控。
- 至少一个模型在真实棋盘上可接受。
- RKNN 若不稳定，则降级为后续实验项。

### Phase 1: Inference Contract + Replay Harness

目标不是先做 UI，而是先把“模型输出可解释”这件事锁死。

交付物：

- `InferenceBackend` 接口
- `export_onnx.py` + `model.meta.json`
- `OnnxBackend`
- 离线 replay harness
- 固定 artifact 的 contract tests

这一步先不要接 UI，不要接 session。

### Phase 2: Vision Worker

把相机、推理、预览编码放到独立 worker。

worker 输出：

- `camera_status`
- `board_lock_status`
- `observed_board`
- `confirmed_move`
- `ambiguity_map`
- `preview_jpeg`

worker 输入：

- `bind_session`
- `set_expected_board`
- `enter_setup_mode`
- `confirm_board_lock`
- `reset_sync`

### Phase 3: Sync State Machine

引入明确状态机，而不是单纯 event list。

建议状态：

- `UNBOUND`
- `CALIBRATING`
- `READY`
- `SYNCED`
- `CAPTURE_PENDING`
- `MISMATCH_WARNING`
- `BOARD_LOST`
- `DEGRADED`

关键原则：

- 新落子只接受 `MoveDetector` 的稳定确认结果。
- `ILLEGAL_CHANGE` 必须要求连续 N 帧稳定不一致，或持续 T 秒。
- `CAPTURE_PENDING` 必须是持续态，直到石子被拿走。
- 棋盘整体位移优先判定为 `BOARD_LOST`，不是 20 个非法变化。

### Phase 4: 按模式集成，而不是一次接三页

推荐顺序：

1. **GamePage**
   - 这是最标准的 session 驱动路径
   - 先只做：校准后自动落子 + 提子提醒 + 相机断开降级
2. **Research**
   - 先补真正的 research session page，再接视觉
   - 最后才做 `重新同步`
3. **Tsumego**
   - 不走 `bind_session`
   - 由前端把 target board 下发给 vision worker
   - setup 完成后，前端本地 hook 继续主导题目逻辑

### Phase 5: UI Hardening

UI 上建议分级处理：

- 非阻塞：
  - 相机连接状态
  - 已校准/未校准
  - AI 落子提示
  - 轻度歧义提示
- 阻塞：
  - tsumego setup 未完成
  - 必须提子后才能继续
  - 棋盘严重异常且不能判断

同时注意 fullscreen `GamePage` 不走 `StatusBar`，需要独立状态提示容器。

### Phase 6: Soak Test + Fallback

最终收口不应是“功能能演示”，而应是“板子上能稳定跑”。

必须验证：

- 30 分钟以上连续运行不泄漏/不卡死
- 相机插拔可恢复
- 浏览器刷新/页面切换后 worker 状态正确
- vision 关闭后 touch-only 路径完全可用

---

## 建议重排后的任务清单

1. 做模型/后端 feasibility gate，而不是直接开始抽象后端。
2. 落 `InferenceBackend + artifact metadata + replay tests`。
3. 实现独立 vision worker 和最小控制面 API。
4. 实现 `ObservedBoard -> SyncStateMachine`，明确与 `MoveDetector` 分工。
5. 先接 `GamePage`，只做最小闭环。
6. 补 research session page，再做 research integration。
7. 最后做 tsumego setup mode，采用前端 expected board 下发模式。
8. 最后再考虑 RKNN、重同步高级语义、更多 UI polish。

---

## 最终建议

如果要一句话总结我的意见：

**Claude 的 v1 适合作为“需求覆盖草案”，不适合作为“直接执行的工程计划”。**

最应该先修正的不是某个 API 名字，而是这三件事：

1. 先做板端 feasibility gate，别在未验证的模型/后端上铺 14 个任务。
2. 先定义清楚 sync state machine，别让 `MoveDetector` 和 `BoardSyncEngine` 重复裁决。
3. 先对齐当前代码基线，尤其是 tsumego、research、fullscreen GamePage 这三处页面形态。

把这三件事修正后，这个项目就会从“风险很高的大计划”变成“可以分阶段落地的小系统”。
