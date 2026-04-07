# Tutorial Module Design Review

Reviewer: Claude Sonnet 4.6
Date: 2026-03-14
Document reviewed: `2026-03-14-tutorial-module-design.md`

---

## Review Summary

设计骨架正确，三层分离、发布包只读、版权隔离的核心判断都站得住脚，但有两个关键实现机制（narration 改写 + 发布包热切换）在文档中完全缺席，无法直接交给工程团队实现。离进入 implementation planning 只差这两个明确说明。

---

## Blocking Issues

### 1. Narration 改写机制未指定

**位置**：Editorial build layer 第 7 步 `Rewrite narration into spoken teaching copy`；`katrain/tutorial_builder/rewrite/`

设计文档明确了"要做改写"，但完全没有说明**谁来改写、用什么工具、以什么方式**。这不是实现细节，是整个 editorial pipeline 的核心环节，直接影响：

- builder 的外部依赖（LLM API？本地模型？人工模版？）
- 改写质量的一致性与可审计性
- 版权防线的强度（机器改写 vs 人工改写，对"不照搬原文"的保障程度完全不同）
- 测试策略（如何验证"不近似复制"？）

**必须在进入 planning 前明确**：使用哪种改写方式，其输出是否需要结构化 schema 约束（如最大字数、口播停顿位置），以及改写失败时的 fallback。

---

### 2. 发布包版本切换机制未指定

**位置**：Error Handling > Publish 部分；`data/tutorials_published/`

设计文档要求"原子发布"并提出"swap the active manifest or directory pointer"，但**没有指定实现方式**。这直接影响：

- 在线服务的 reload 策略：服务启动时从固定路径加载，热更新需要 reload 信号还是重启？
- `katrain/web/tutorials/loader.py` 的设计（每次请求读磁盘？启动时缓存？）
- 运维流程：如何确认一次 publish 是否生效？如何回滚？

可选方案（设计文档需要选一个）：
- 符号链接 `current -> v3/`，切换时原子重指
- `manifest.json` 包含版本号，服务定期 poll 或接收 SIGHUP reload
- 固定路径 + 服务器重启（Phase 1 最简方案）

---

## Risks and Gaps

### R1. Step 字段语义冲突：`image_asset` vs `board_payload` 在 Phase 1 中重叠

**位置**：Data Model > Step

Phase 1 `board_mode=image` 时，Step 同时有 `image_asset` 和 `board_payload` 两个字段。前端渲染到底读哪个？设计没有说清楚。

建议：明确 Phase 1 只使用 `image_asset`，`board_payload` 在 `board_mode=image` 时为 null；升级 SGF 后，`board_payload` 才作为主字段，`image_asset` 可废弃。否则实现者会自行决定，前后端可能不一致。

---

### R2. Topic 去重算法被整体推迟，但它是最高风险模块

**位置**：Editorial build layer 第 4 步；`katrain/tutorial_builder/dedupe/`；Open Follow-up 第 1 条

跨书去重是整个 pipeline 中技术难度最高、主观判断最多的部分。当前设计将"exact dedupe heuristics"完全推到 Open Follow-up。这可以接受，但建议在进入 planning 前至少明确：

- 去重的粒度（按关键词匹配？嵌入相似度？人工标注？）
- 去重的最坏情况处理策略（即"无法确认是否重复"时，保留两个 example 还是强制合并？）

否则 `dedupe/` 子包的实现边界在 planning 阶段会无法定义工作量。

---

### R3. CosyVoice 集成细节缺失

**位置**：TTS Integration；`katrain/tutorial_builder/tts/`

设计文档说 CosyVoice 支持 batch/service 模式，但以下问题未指定：

- 使用哪个接口：HTTP FastAPI 还是 gRPC？
- 目标语音：预设音色还是克隆音色？
- 中文文本规范化：CosyVoice 的中文 TN 是否满足围棋术语（如"三三"、"天元"、"小目"的正确读音）？
- Phase 1 是否有 GPU 资源？还是使用 CPU 模式（速度差异巨大）？

这些是 builder 开发者第一天就会问的问题。

---

### R4. UserProgress 恢复语义未定义

**位置**：Data Model > UserProgress

`last_step_id` 足够支持"恢复到上次位置"，但以下场景未定义：

- 用户到达最后一个 step，是否自动标记 `completed=true`，还是需要主动操作？
- 用户再次进入一个 `completed` 的 example，是从头还是从最后一步？
- Step 是否有 `completed_steps[]` 记录（现在没有），还是只靠 `last_step_id` 推断？

这些不影响数据库 schema，但影响前端 playback 组件的状态机设计，建议 planning 前说清楚。

---

### R5. 截图版权风险未被文档认可

**位置**：Non-Goals；Content policy

文档在 Non-Goals 里写了"不暴露书名作者"，在 Content policy 里写了"avoid near-verbatim reproduction"，但对截图本身的版权风险只字未提。

**事实**：书中截图（包含棋盘图例）是受著作权保护的美术作品，即使不标注来源，用于商业产品仍有侵权风险。这比文字改写的风险更直接，因为截图是 1:1 复制，无法"改写"。

建议设计文档明确：
- 这是一个已知的法律风险，Phase 1 暂时接受（并写明接受理由，如"仅内测"或"教育目的主张合理使用"）
- 或者，明确 Phase 1 的截图来源限制（如只用无版权插图、自制棋盘图等）

---

### R6. `Example.total_duration_sec` 存在 pipeline 依赖顺序问题

**位置**：Data Model > Example

该字段是各 Step 音频时长之和，但音频是 TTS 生成的，生成顺序在 narration 之后。这意味着该字段只能在 TTS 完成后回填。pipeline 需要在 publish 阶段计算并写入，而非 draft 阶段。如果实现者在 draft 阶段就期望这个字段存在，会产生 bug。

建议：在 DraftExample 中明确该字段为 nullable，仅在 TTS 完成后填充。

---

## Over-Engineering Check

### 可能过度设计的部分

**`katrain/tutorial_builder/` 的 7 个子包结构**

```
ingest / normalize / dedupe / rewrite / tts / review / publish
```

Phase 1 需要先跑通一条端到端链路，7 个子包在 planning 时需要分别定义接口，增加协调成本。建议从单一的 `tutorial_builder/pipeline.py` 或 2-3 个模块开始，等真正遇到需要分离的边界再拆。

**`Topic.estimated_minutes`、`Topic.difficulty`、`Topic.tags[]`**

Phase 1 验收标准是"1 个 category + 1 个 topic + 1 个 multi-step example 跑通"。这三个字段不在验收标准内，而且 `estimated_minutes` 依赖 TTS 完成后才能准确，`difficulty` 的分级标准本身就需要额外定义。建议 Phase 1 留空并标记 TODO，不在 schema 中强制要求。

**`Category.cover_asset`**

Phase 1 可能只有 1-2 个分类，占位图片即可。不需要在第一版发布包里强制这个字段。

### 合理的前瞻设计（不应删除）

- **`Step.board_mode` 枚举字段**：这是最小代价的演进预留，避免未来加 SGF 时重构页面层级，保留是对的。
- **发布包原子切换**：防止线上读到半成品，Phase 1 就要做，不是过度设计。
- **私有/公开对象分离**：这是整个版权安全策略的基础，不是可选的。
- **三层架构**：离线生成 + 人工审核 + 只读服务，对 Phase 1 而言是正确的复杂度。

---

## Recommended Adjustments

1. **在设计文档里新增 "Narration Rewrite Mechanism" 小节**，说明使用什么工具（如 LLM + prompt template）、输入/输出 schema、改写失败的处理。哪怕 Phase 1 是"人工改写"也要明确写出来。

2. **在 Error Handling > Publish 小节里选定一种热切换方案**并说明理由。Phase 1 如果接受"重启服务器"作为 reload 策略，明确写出来；如果要做符号链接，就说明 loader.py 如何感知。

3. **在 Data Model > Step 里澄清 `image_asset` 和 `board_payload` 的关系**：Phase 1 `board_mode=image` 时，`board_payload` 为 null，前端只读 `image_asset`。

4. **在 Content policy 里增加一条关于截图版权的说明**，明确这是已知风险以及团队的接受理由或缓解方案。

5. **将 `Tutorial Builder` 的代码结构从 7 个子包简化为更平铺的初始结构**，例如：
   ```
   katrain/tutorial_builder/
     pipeline.py     # 主流程协调
     ingest.py       # source fragment 提取
     build.py        # topic/example/step 构建 + dedupe
     tts.py          # CosyVoice 调用
     publish.py      # 发布验证 + 包写出
   ```
   等到第一个端到端跑通后再按需拆分。

6. **在 Open Follow-up 的"dedupe heuristics"条目下，增加至少一个候选方案描述**（不需要选定，但要让实现者知道从哪里开始思考）。

---

## Verdict

**Needs design revision before planning**

原因：两个 Blocking Issue（rewrite 机制 + 热切换机制）需要补充说明，否则 implementation planning 无法定义这两个模块的工作边界。Gap 不大，补充说明后可以直接进入 planning。
