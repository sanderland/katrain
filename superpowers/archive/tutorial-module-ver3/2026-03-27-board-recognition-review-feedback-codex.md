# Tutorial Module Stage 3 棋谱识别方案审核反馈

整体判断：这份方案的主方向是对的，尤其是“几何定位交给 CV，语义识别交给更强模型”这个拆分，明显比整页直接丢给视觉模型更务实。但当前版本仍有几处会直接影响落地质量的缺口：区域校准过度依赖星位、批量写库路径与 Stage 2 的服务端约束不一致、训练数据闭环会把噪声直接放大，以及 Phase 2 的数字建模与原始需求 `1-99+` 并不一致。如果不先补这些点，Phase 1 很可能能“跑起来”，但很难稳定产出可直接入库的 `board_payload`。

## 关键结论

- 方案可做，但不建议按当前文本原样推进。优先级最高的不是再加模型，而是先补“校准鲁棒性 + 数据闭环 + 写库语义一致性”。
- `cv_detect_star_points()` 只能作为证据之一，不能作为主校准锚点。星位被占、局部图不含星位、或中腹局部图时，这条链路会退化。
- 训练集方案存在明显自相矛盾：Phase 2 需要 `empty` 类，但 Step 4.1 明确跳过 `empty` 样本保存，后续模型会天然偏置。
- 当前仓库里 `PUT /figures/{id}/board` 会做乐观锁和 `viewport` 计算，但脚本实际写库走的是 `db_queries.update_figure_board()` 直写 DB，不经过 API；这会让计划里对 409 冲突和服务端字段回填的假设失真。
- 验收口径也需要先统一。计划里图 4 的“参考真值”与前面现状分析里的 8 子真值不一致，当前文档自身就有一处测试 oracle 漏子。

---

## 一、架构合理性

### 1. “CV 定位 + VLLM 分类”的职责分离是否合理？
**判定：** ⚠️

**说明：**
- 大方向合理。CV 负责像素级网格与交叉点定位，这一层比 VLLM 更可控。
- 但当前文本把 VLLM 放成了每个 occupied patch 的默认分类器，这个分工仍然过重。很多 patch 上，`empty / black / white-ring` 其实是可以用确定性方法先做掉的。
- 更稳妥的分层应该是：`CV 几何` → `轻量规则/小模型做大多数 patch 分类` → `VLLM 只处理低置信度和 OCR 困难样本`。

**建议：**
- Phase 1 就引入 `unknown / needs_review` 桶，不要强迫 VLLM 对每个 patch 给硬分类。
- 把 VLLM 从“默认分类器”降级为“歧义裁决器 + OCR 兜底器”。

### 2. Contact sheet 是否是批量发给 VLLM 的最优方案？
**判定：** ⚠️

**说明：**
- 对“人工驱动的 bootstrap 阶段”来说，contact sheet 很实用，便于一次看完整个 figure，也方便人工复核。
- 但它不是自动化流水线里的最优长期方案。把多个小图拼到一张图里会牺牲单 patch 的有效分辨率，标签文本还会占空间并干扰模型注意力。
- `JSON base64` 不是更好方案，多图 API/SDK 调用或单图 + 附带放大裁剪，通常更稳。

**建议：**
- 保留 contact sheet 作为 QA/人工复核产物。
- 对自动分类，优先考虑“原始 patch + 放大版 patch + 结构化输出 schema”的 SDK 调用，而不是 subagent 人工回传 JSON。
- 若继续用 contact sheet，至少对疑难 patch 追加单独 zoom-in 图。

### 3. `occupied` 宽松检测 + VLLM 端 `empty` 过滤是否合理？
**判定：** ⚠️

**说明：**
- 这是正确的 recall-first 思路，因为漏检是不可恢复错误，误检还可以后过滤。
- 但当前计划没有定义 recall 目标、误检上限、以及二次补扫策略。只有“宁多不漏”还不够，必须量化。
- 另外，VLLM 输出里缺少 `unknown` 类，会迫使模型在不确定时瞎选，反而把假阳性洗成“真标签”。

**建议：**
- 明确指标：例如 occupied recall 必须接近 100%，误检率可容忍但要可审查。
- 增加 `unknown` 类，并把低置信度 patch 进入人工复核队列。
- 对所有“接近阈值但未入选”的交叉点增加二次检查，而不是单次阈值截断。

### 4. 星位校准方案是否足够鲁棒？
**判定：** ❌

**说明：**
- 不足够。问题不只是“星位上可能有棋子”，还包括：局部图可能完全不含星位、中腹图多个 offset 都可解释、以及星位本身可能因扫描/印刷变浅。
- 计划在 `board-recognition-plan.md:487-549` 中把星位检测当主路径，这会在很多真实局部图上失效。
- 更关键的是，方案没有把“边界线是否为棋盘边框”“可见行列数”“角/边/中腹类型”纳入同一套假设搜索。

**建议：**
- 把区域映射改成“多证据假设搜索”：可见行列数、边框粗线、角部形态、星位、已知棋盘总 size 一起约束 `col_start / row_start`。
- 输出不仅要有 `col_start / row_start`，还要有 `confidence` 和 `evidence`。
- 对低置信度 figure 不直接入库，进入待审队列。

---

## 二、CV 技术方案

### 5. gap-fill 的 `gap > 1.6× spacing` 会不会误触发？
**判定：** ✅

**说明：**
- 作为启发式规则本身是合理的，而且现有 `cv_detect_grid()` 已经在仓库脚本中验证过一轮，方向没问题。
- 它真正的风险不在棋盘边缘，而在“局部透视畸变 + 棋线弱化”时把不均匀 spacing 误判成缺线。

**建议：**
- 触发条件里加一层“接近整数倍 spacing”的约束，不要只看 `> 1.6x`。
- 补一个 guard：补线后总行列数不得超过 19，也不得与边框检测结果矛盾。
- 用 golden set 覆盖“遮挡严重 / 边角局部 / 扫描变形”三类样本。

### 6. Occupied 多维特征阈值的跨书泛化能力如何？
**判定：** ⚠️

**说明：**
- 当前阈值明显是按单书校出来的，跨出版社、不同纸色、扫描对比度时会漂。
- 方案里虽然用了相对统计量（median/std），但仍然混入了固定绝对阈值，如 `circ < -15`、`dark > 0.28`，这部分泛化风险仍然存在。

**建议：**
- 先做每图级别的亮度/对比度归一化，再算特征。
- 用自适应阈值或 per-book calibration profile，而不是只保留一套全局 magic numbers。
- 把“空交叉点特征分布”单独建模，用空点背景去校正当前图的阈值。

### 7. 50×50 px 裁剪是否足够？
**判定：** ⚠️

**说明：**
- 对“是否有子”可能够，对“两位数 OCR”明显偏冒险。
- 计划里写的是 50×50，但实际 spacing 约 39px，等于基本没有信息放大；对 `10+`、`99` 这类数字，VLLM 的读取稳定性会很差。

**建议：**
- 裁剪窗口至少取 `1.4x~1.8x spacing`，然后统一 resize 到 `80~96px`。
- 同时生成两套输入：原图 patch 和增强版 patch（CLAHE/锐化/二值化）。
- 对数字 OCR 单独准备居中放大的 ROI，而不是复用分类 patch。

### 8. 棋图 bbox 的 CV 投影分析是否足够鲁棒？
**判定：** ✅

**说明：**
- 在“每页 2 张图、左图右文、版式相对固定”的前提下，CV 投影分析应当是主路径，成本低且可解释。
- VLLM 画 bbox 可以作为兜底，但不应该是默认主方案。上游 bbox 一旦漂，后续网格、校准、OCR 全部一起漂。

**建议：**
- 继续以 CV 版面分析为主，VLLM 仅作为“异常页”备选。
- 给 bbox 检测加简单的版面 sanity checks：宽高比、左侧占比、与图号的相对位置关系。

---

## 三、VLLM 分类方案

### 9. 8 类设计是否完备？
**判定：** ❌

**说明：**
- 当前 taxonomy 不完备，至少缺 `unknown / unreadable`。
- 如果后续真要接前端编辑器能力，还缺 `square`、`circle` 这类图形类；当前 Stage 2 前端已经支持 `triangle/square/circle`。
- 对 OCR 结果也缺显式失败态，例如 `white+?`、`digit_on_empty`、`mark_on_stone_unresolved`。没有这些中间态，错误会被硬压成错误真值。

**建议：**
- 类别拆成两层：`base_type` 和 `attributes`，而不是把所有语义拼成一个扁平字符串。
- 至少增加 `unknown`、`ocr_failed`、`shape_square`、`shape_circle`。
- 如果当前需求范围只想支持三角，也建议在 schema 里为后续图形留扩展位。

### 10. VLLM subagent 调用效率是否可接受？
**判定：** ⚠️

**说明：**
- 200+ figures、每 figure 10~20 秒，串行就是 33~67 分钟；算上重试、人工调度、输出整理，实际更接近 1~2 小时。
- 如果人工开 5 个 subagents 并行，纯推理时间可以降，但这仍然不是稳定的工程化批处理方式。
- 计划把“人工 subagent 分类”写成 Phase 1 主链路，这更像运营流程，不像可复跑的 pipeline。

**建议：**
- Phase 1 可以接受，但要明确这是 bootstrap 模式，不是正式生产模式。
- 尽早把分类调用收敛成一个可脚本化的接口，至少支持重试、超时、schema 校验、日志留存。
- 对全书批处理优先做“只跑疑难 patch”的 fallback 设计，别让所有 patch 都走 VLLM。

### 11. VLLM 在 contact sheet 上读 `1-99` 是否可靠？
**判定：** ❌

**说明：**
- 在 `~40px` 级别 patch 上直接读两位数，风险太高。
- 特别是白子上的深色数字，本来就容易和黑子分类互相干扰；若再叠加 contact sheet 缩放，错误率会被放大。
- 当前计划没有给 OCR 加专门预处理，只是让一个分类 prompt 顺手把数字也读了，这不稳。

**建议：**
- 数字 OCR 与石子类型分类分开做。
- 先做 patch 放大、对比度增强、中心区域裁切，再交给 OCR 模块。
- 对 `>= 10` 的数字单独做高分辨率识别，不要与普通黑白分类共享同一视觉输入。

---

## 四、Phase 2 模型训练

### 12. EfficientNet-B0 是否是最优小模型？
**判定：** ⚠️

**说明：**
- 作为 baseline 可以，但谈不上“最优”。
- 这种 patch 分类任务的输入非常小、语义结构很强，MobileNetV3 或 ResNet18 反而可能更容易训稳，CPU 推理也更轻。
- ViT-Tiny 对当前数据规模大概率不划算。

**建议：**
- 不要先拍死骨干网络。先并排做 `MobileNetV3-Large / ResNet18 / EfficientNet-B0` 的小规模基准。
- 比较的指标不要只看准确率，还要看 CPU 延迟、模型大小、对噪声扫描的鲁棒性。

### 13. `~2000` 样本估算是否合理？类别不平衡如何处理？
**判定：** ❌

**说明：**
- 以当前设计，不合理。因为 `board-recognition-plan.md:441-467` 的 `save_training_patches()` 会直接跳过 `empty`，而 Phase 2 类别列表 `board-recognition-plan.md:574-582` 却要求训练 `empty` 类。
- 也就是说，按现计划收数据，模型从一开始就拿不到最关键的负样本。
- 即便不算 `empty`，`triangle_*`、`letter`、大编号两位数样本也会极度稀缺，2000 总量远不足以支撑 8 类 + OCR 头的稳定训练。

**建议：**
- 明确按类设配额，而不是只看总样本数。
- 主动采集 hard negatives：误检空点、边框、文字、星位、污点。
- 在 manifest 里记录 class distribution，训练时做 class-balanced sampling 或 focal loss。

### 14. 8 类分类头 + `0-99` 数字头的双头设计是否合理？
**判定：** ❌

**说明：**
- 与原始需求不一致。需求是 `1-99+`，而计划数字头是 `0-99`，这在 `100+` 时直接失效。
- 把数字做成 100-way 单分类也不优雅，尤其在样本很少时很难训稳。
- 语义上更适合拆成“有无编号 + 逐字符识别”，或者单独 OCR 模型。

**建议：**
- 数字识别改成两位/三位字符序列头，或独立 OCR 模块。
- 主模型先只做 `empty / black / white / triangle / letter / numbered_stone / unknown` 这类粗分类。
- 对 `numbered_stone` 再调用专门数字识别分支。

### 15. VLLM 标注错误如何避免传播到训练集？
**判定：** ❌

**说明：**
- 当前计划是“自动保存即入训练集”，这会把 Phase 1 的误判直接固化成监督信号。
- 而且现有目录设计只保存“图片放到类目录”，没有保存来源、置信度、版本、复核状态，后面几乎没法清洗。

**建议：**
- 训练集至少分三层：`raw_auto`、`reviewed`、`gold`。
- 只有人工确认或多模型高一致性的样本，才进入正式训练集。
- 记录完整 provenance：书、页、figure、局部坐标、全局坐标、提示词版本、模型版本、生成时间、复核人。

---

## 五、工程实现

### 16. `recognize_boards_v2.py` 单文件是否会过于臃肿？
**判定：** ⚠️

**说明：**
- 会。当前这个文件已经同时承载了 CV、VLLM 调用、DB 写入、CLI、调试输出，继续叠功能会迅速失控。
- 仓库现状也已经证明这一点，`scripts/recognize_boards_v2.py` 里 Step 0~5 都耦在一起，可测试性很弱。

**建议：**
- 现在就拆，不要等 Phase 2 再拆。
- 至少拆成 `cv_pipeline.py`、`classification.py`、`calibration.py`、`payload_builder.py`、`pipeline_runner.py`。
- 把“纯函数部分”独立出来先补单元测试。

### 17. 自动保存训练数据的目录结构是否合理？
**判定：** ❌

**说明：**
- 仅按类目录落盘不够。后面你会需要追溯“这个 patch 来自哪一页、哪个 figure、何种 preprocess、谁标的、有没有人工修正”。
- 当前方案也没有保存 `label_map`、grid spacing、crop 参数、原图路径，后续无法复现。

**建议：**
- 采用 `manifest.jsonl` 或 CSV + 图片文件的设计。
- 每条记录至少包含：`patch_id`、`book/page/figure`、`local_coord`、`global_coord`、`class`、`number`、`source`、`confidence`、`review_status`、`preprocess_version`、`image_path`。
- 图片目录不要只按类切，也要保留按来源检索的能力。

### 18. 某个 figure 分类失败时，应该怎么处理？
**判定：** ⚠️

**说明：**
- 不应中断整本书，也不应静默跳过。
- “CV fallback”只能解决几何问题，不能解决 VLLM/OCR 的语义失败，所以不能把所有失败都归到 CV fallback。

**建议：**
- 定义 per-figure 状态：`success`、`needs_review`、`failed_cv`、`failed_semantic`。
- 一本书继续处理，但产出 summary report，明确哪些 figure 未入库。
- 失败 figure 的 contact sheet、原图 crop、日志、模型输出都要保留，便于人工复核。

### 19. 新书处理流程是否足够清晰？
**判定：** ❌

**说明：**
- 当前方案对工程师是清楚的，对操作者并不清楚。尤其“导出 contact sheet → 调 subagent → 手动收集 JSON → 再 apply”这一段，人工步骤太多。
- 非技术人员无法稳定执行，也不容易复跑和审计。

**建议：**
- 封装成单一 CLI 或后台任务流：
  `prepare` → `classify` → `review-ambiguous` → `apply` → `report`
- 每一步都有明确输入输出目录和状态文件。
- 给出“最少几步”的操作手册，而不是让操作者拼命令。

---

## 六、与 Stage 2 的集成

### 20. `update_figure_board()` 的乐观锁是否会在批量写入时触发 409？
**判定：** ❌

**说明：**
- 按当前仓库实现，脚本并不会触发 409，因为它走的是 `katrain/web/tutorials/db_queries.py:88-93` 的直写 DB，而不是 `katrain/web/api/v1/endpoints/tutorials.py:133-162` 的 API。
- 这意味着计划里对“是否会 409”的讨论前提其实没有落在现有实现上。
- 如果后面改成走 API，则在人机并行编辑时确实会遇到 409。

**建议：**
- 不要让脚本直接写 DB，抽一个共享 service，统一处理 `expected_updated_at`、`viewport` 计算和审计日志。
- 如果批处理阶段默认是“只填充原先为 NULL 的 payload”，就加 `skip_if_not_null` 或 compare-and-set 语义。

### 21. 识别结果中是否需要包含 `highlights`？固定 `[]` 是否正确？
**判定：** ⚠️

**说明：**
- `highlights: []` 本身没问题，前端和现有类型定义也能接受空数组。
- 真正的问题不是 `highlights`，而是 `viewport`。Stage 2 的 API 会在保存时自动计算 `viewport`，但当前批处理脚本若直写 DB，不会得到这个字段，前端会回退成全盘显示。

**建议：**
- 继续写 `highlights: []`。
- 但在真正入库前，必须统一调用 `compute_viewport()` 或复用 Stage 2 的保存服务，不要只存裸 payload。

### 22. 用户修正后的数据是否应该反哺训练集？
**判定：** ⚠️

**说明：**
- 应该反哺，而且这会比 VLLM 自动标签更有价值。
- 但不能“所有前端保存都直接进训练集”，否则会把实验性编辑、半成品修改、甚至误操作一并吸进去。

**建议：**
- 保存“识别前 payload / 识别后 payload / 用户最终 payload”的 diff。
- 只有用户明确确认过的修正才进入 `reviewed` 或 `gold` 数据集。
- 前提是 Phase 1 就要把 patch 与 board 坐标、figure id 建好稳定映射，否则后面无法把人工修正回投到 patch 级样本。

---

## 我建议的修订版落地顺序

1. 先补校准与写库语义：统一 `col_start/row_start` 推断接口、统一 `compute_viewport` 与 compare-and-set 写入。
2. 重构脚本边界：先把单文件拆成可测试模块。
3. 把 Phase 1 的语义输出改成 `class + confidence + unknown`，别直接硬入库。
4. 训练数据先做 manifest/provenance，再谈模型训练。
5. VLLM 先只承担困难样本和 OCR 兜底，别让它成为所有 patch 的主分类器。
6. 等 golden set 指标稳定后，再决定 EfficientNet/MobileNet 哪个更合适。

## 建议补充的验收指标

- grid line exact-match rate
- occupied recall / false-positive rate
- black/white classification accuracy
- numbered stone OCR accuracy
- annotation accuracy（triangle / letter）
- end-to-end `board_payload` exact match rate
- `needs_review` 占比

## 补充发现

- `board-recognition-plan.md:441-467` 的训练数据保存逻辑会跳过 `empty`，但 `board-recognition-plan.md:574-582` 又要求训练 `empty` 类，这是当前文档内部的直接矛盾。
- `board-recognition-plan.md:407-416` 图 4 的参考结果少写了一颗黑子，和前面“8 颗棋子全部正确”的现状分析不一致。建议先统一黄金真值，再做后续自动化验证。
