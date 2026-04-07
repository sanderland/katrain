# Tutorial Module Plan Review Prompt

请审阅下面这份开发设计，目标是帮助我发现其中的漏洞、遗漏、过度设计、边界不清和实施风险。

你的角色不是重写方案，而是作为一个严谨的高级工程师/架构评审，判断这份设计是否已经足够进入 implementation planning。

---

## 1. 项目背景

我在做一个围棋学习产品，基于 KaTrain Web 的 Galaxy UI，准备新增一个全新的“教程”模块。它与现有的“对弈 / 直播 / 死活题 / 棋谱库”等模块平行，是一个正式的新模块，而不是现有模块的附属页面。

现有书籍内容已经在另一个路径下完成了解析。以这个例子为参考：

- `/Users/fan/Repositories/go-topic-collections/books/布局/曹薰铉布局技巧_上册_曹薰铉_1997/output/book.json`
- `/Users/fan/Repositories/go-topic-collections/books/布局/曹薰铉布局技巧_上册_曹薰铉_1997/output/review.html`

这些书籍解析结果包含章节、页面、图例、截图等信息。现在要做的是：基于 `book.json` 和截图，生成一个正式的教程模块，而不是继续停留在单本书的 review 页面。

---

## 2. 用户原始需求

需求来自以下约束和目标：

1. 要把书籍解析结果做成“有声教程”。
2. TTS 可以使用 Alibaba 开源的 CosyVoice 项目作为语音生成模块。
3. 这是一个全新的教程模块，平行于“对弈 / 直播 / 死活题”等模块。
4. 第一阶段可以继续使用书中的截图作为视觉材料。
5. 未来可能把截图升级成 SGF 交互棋盘，但不是第一阶段重点。
6. 教程模块不能提及书名，因为可能会有版权风险。
7. 书中的语言不能直接照搬，需要进行转换：
   - 避免照搬原文的嫌疑
   - 让文案更适合朗读
   - 去掉书面腔、冗余、特殊符号、OCR 噪音
8. 教程模块的大分类大体按围棋学习阶段划分，例如：
   - 入门
   - 布局
   - 中盘
   - 官子
9. 每个分类下面可能会涉及多本书、不同作者的内容。
10. 不同书里如果章节内容相似，不应机械按“书 -> 章”展示，而应做内容归并。
11. 用户确认后的公开层级是：

```text
教程
  -> 分类（入门 / 布局 / 中盘 / 官子 ...）
    -> topic（具有独立教学意义的主题，不等于书章节）
      -> example（一个或多个例子）
        -> step（最小播放单元）
```

12. 用户还确认了这些关键约束：
   - Phase 1 只做 Web
   - 前后端都要实现
   - 内容生成必须离线完成
   - 音频必须离线生成
   - 发布前必须人工审核
   - 第一阶段人工审核可以是离线文件审核，不需要先做 CMS

---

## 3. 当前设计方案摘要

目前的设计方案核心如下。

### 3.1 总体架构

采用 3 层架构：

1. **Private source layer**
   - 保存原始 `book.json`、`review.json`、截图、原始文本、来源路径等
   - 这些信息不进入公开 API，也不进入公开 UI

2. **Editorial build layer**
   - 离线构建器读取原始解析结果
   - 抽取 source fragments
   - 做分类归类
   - 做 topic 去重归并
   - 拆分 example 和 step
   - 生成适合口播的改写文案
   - 调用 CosyVoice 生成音频
   - 产出 draft
   - 人工审核
   - 发布成公开教程包

3. **Public app layer**
   - KaTrain Web 的新教程模块只读取“已发布教程”
   - 负责浏览分类、topic、example、播放 step、记录学习进度
   - 不负责实时生成内容

### 3.2 数据建模

内部离线对象包括：

- `SourceFragment`
- `DraftTopic`
- `DraftExample`
- `DraftStep`
- `ReviewRecord`

公开线上对象包括：

- `Category`
- `Topic`
- `Example`
- `Step`
- `UserProgress`

关键点：

1. 公开数据不含书名、作者、译者、原始页码标题、原始文本。
2. `Step` 里会保留：
   - narration
   - image_asset
   - audio_asset
   - `board_mode`
   - `board_payload`
3. `board_mode` 第一阶段是 `image`，以后可以扩展成 `sgf`，从而不重构页面层级。

### 3.3 发布包结构

建议采用发布包结构，例如：

```text
data/tutorials_published/
  manifest.json
  categories/
  topics/
  examples/
  assets/images/
  assets/audio/
```

线上服务读发布包，不直接读原始书籍解析目录。

### 3.4 代码落点

建议新增：

```text
katrain/tutorial_builder/
  ingest/
  normalize/
  dedupe/
  rewrite/
  tts/
  review/
  publish/
```

线上后端：

```text
katrain/web/tutorials/
katrain/web/api/v1/endpoints/tutorials.py
```

线上前端：

```text
katrain/web/ui/src/galaxy/api/tutorials.ts
katrain/web/ui/src/galaxy/types/tutorials.ts
katrain/web/ui/src/galaxy/pages/tutorials/
katrain/web/ui/src/galaxy/components/tutorials/
```

并接入 Galaxy 路由和 Sidebar。

### 3.5 API 方向

推荐 Phase 1 的 API 形状：

- `GET /api/v1/tutorials/categories`
- `GET /api/v1/tutorials/categories/{slug}/topics`
- `GET /api/v1/tutorials/topics/{topic_id}`
- `GET /api/v1/tutorials/examples/{example_id}`
- `GET /api/v1/tutorials/progress`
- `POST /api/v1/tutorials/progress/{example_id}`

### 3.6 风控策略

方案里明确要求：

1. 公开层绝不出现书名、作者、译者、来源路径、原始章节名。
2. narration 必须是改写后的最终口播稿。
3. 人工审核是发布前硬门槛。
4. 如果改写失败、TTS 失败、截图缺失，则不能进入 published。
5. 发布必须原子化，避免线上读到半成品。

### 3.7 测试与验收

设计中已经提出：

1. Builder 测试
   - `book.json -> fragments`
   - dedupe 稳定性
   - forbidden fields 不进入 publish
   - image/audio/board consistency

2. Backend 测试
   - tutorial endpoints schema
   - 404 / refresh / progress 逻辑

3. Frontend 测试
   - sidebar 接入
   - category -> topic -> example 导航
   - 音频播放与 step 切换
   - `board_mode=image` 展示

4. 验收目标
   - 至少 1 个分类、1 个 topic、1 个多 step example 跑通全链路
   - 公开层不暴露书信息，不照搬原文
   - 用户能完成“看图 + 听讲 + 切 step + 记录进度”

---

## 4. 当前完整设计文档

完整设计文档在这里：

- `/Users/fan/Repositories/katrain-tutorials/superpowers/tracks/tutorial-module/2026-03-14-tutorial-module-design.md`

请以这份文档为主，如果你发现我上面的摘要和设计文档不一致，请指出不一致之处。

---

## 5. 你的审阅任务

请你重点审查以下内容：

### A. 需求匹配

1. 这份设计是否准确响应了原始需求？
2. 是否有遗漏的硬约束？
3. 是否有与需求相冲突的设计点？

### B. 架构合理性

1. 3 层结构是否合理？
2. “离线构建器 + 发布包 + 线上只读服务”是否是适合 Phase 1 的做法？
3. 是否有职责边界不清的模块？
4. 是否存在不必要的复杂度？

### C. 数据模型与可演进性

1. `Category -> Topic -> Example -> Step` 是否合理？
2. Topic 去重归并的边界是否清晰？
3. `Step.board_mode = image | sgf` 的演进设计是否合理？
4. 是否有关键字段缺失？

### D. 版权与内容风险

1. 当前设计对“不能提书名、不能照搬原文”的处理是否足够？
2. 是否还缺少应当加入的技术/流程防线？
3. “截图可用但不强调来源”的策略是否有明显风险点？

### E. 实施与测试风险

1. 这个方案是否可以顺利进入 implementation planning？
2. 是否拆分得足够好，适合进入多步骤开发计划？
3. 哪些部分最容易在实现时失控？
4. 是否还缺少必须提前澄清的问题？

### F. YAGNI / 过度设计

1. 哪些内容对第一阶段来说过重？
2. 哪些设计是合理预留，而不是过度设计？

---

## 6. 输出格式要求

请按下面格式输出：

```markdown
## Review Summary

一句话总结你对这份设计成熟度的判断。

## Blocking Issues

- 列出会阻止进入 implementation planning 的问题
- 如果没有，明确写 `None`

## Risks and Gaps

- 列出非阻塞但重要的风险、遗漏、模糊点

## Over-Engineering Check

- 哪些地方可能过度设计
- 哪些地方是合理预留

## Recommended Adjustments

- 给出你建议修改的设计点
- 请尽量具体，指出应该改哪一层、哪一段、哪个接口、哪个数据对象

## Verdict

只能二选一：
- Ready for implementation planning
- Needs design revision before planning
```

---

## 7. 审阅原则

请你：

1. 不要只是泛泛而谈，要尽量指出具体问题。
2. 优先找真正会影响后续实现和交付的问题。
3. 站在“要把这个方案交给工程团队执行”的角度审查。
4. 如果你觉得这个方案总体正确，也请指出最值得警惕的 3 个风险。

