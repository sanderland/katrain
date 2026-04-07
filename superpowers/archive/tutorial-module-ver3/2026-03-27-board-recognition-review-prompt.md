# Tutorial Module Stage 3 — Board Recognition Design Review Prompt

请你作为一名资深计算机视觉工程师和围棋软件架构师，审核以下实施计划。审核时请同时参考**原始需求**、**现状分析**和**实施计划**，逐项检查是否有遗漏、矛盾或可改进之处。

---

## 原始需求

### 背景

KaTrain 教程模块已完成两期开发：
- **Stage 1**：JSON 文件驱动的教程展示 + 只读 SVG 棋盘
- **Stage 2**：数据库存储（PostgreSQL）+ 可编辑 SVG 棋盘 + 整页截图展示 + 书籍导入脚本

Stage 2 完成后，每个 figure（变化图）的 `board_payload`（棋盘数据）仍为 `NULL`，需要人工在前端编辑器中逐一摆子。一本书有数百张棋谱，人工标注不可行。

**Stage 3 的核心目标**：自动识别书中印刷的棋谱图，将其转化为 `board_payload` JSON 写入数据库。

### 需要识别的元素

| 元素 | 示例 | 对应 board_payload 字段 |
|------|------|------------------------|
| 黑棋（无编号） | ● | `stones.B: [[col, row]]` |
| 白棋（无编号） | ○ | `stones.W: [[col, row]]` |
| 黑棋 + 落子序号 | ❶❸❺ 或带数字的实心圆 | `stones.B` + `labels: {"col,row": "1"}` |
| 白棋 + 落子序号 | ❷❹❻ 或带数字的空心圆 | `stones.W` + `labels: {"col,row": "2"}` |
| 三角标记 | △ 在黑子/白子上 | `stones` + `shapes: {"col,row": "triangle"}` |
| 字母标注 | A, B, C 在空交叉点上 | `letters: {"col,row": "A"}` |

### 输入数据

- 页面截图：`data/tutorial_assets/{book_slug}/pages/page_NNN.png`（1655×2382 px）
- 每页通常包含 2 张棋谱图（上下排列），右侧为文字说明
- 棋谱图通常只展示棋盘的**部分区域**（如左半、左上角、四分之一等），不是完整 19×19
- 棋盘网格线质量良好（印刷品扫描），但有轻微扭曲
- 黑棋为实心圆，白棋为空心圆，数字印在棋子上

### board_payload 格式

```json
{
  "size": 19,
  "stones": {"B": [[2, 16], [4, 3]], "W": [[3, 3], [4, 2]]},
  "labels": {"4,3": "1", "4,2": "2", "5,3": "3"},
  "letters": {"5,5": "A"},
  "shapes": {"7,7": "triangle"},
  "highlights": []
}
```

坐标系：col=0 最左列，row=0 最上行。星位（hoshi）固定在 (3,3)(9,3)(15,3)(3,9)(9,9)(15,9)(3,15)(9,15)(15,15)。`viewport` 字段由服务端计算，不在 payload 中。

### 约束

- 棋盘网格精度要求高：棋子必须精确落在正确的交叉点上，±1 偏差不可接受
- 黑白分类必须准确：白棋带深色数字不能误判为黑棋
- 需要支持落子序号（1-99+）的 OCR
- 需要支持三角/字母等特殊标注的识别
- 处理速度要合理：一本书（200+ 页）的处理时间应在可接受范围内

---

## 现状分析

### 已尝试的方法及其问题

#### 方法 1：纯 VLLM 识别（已废弃）

直接将整页截图发给视觉大模型（Claude Opus），要求输出棋子坐标。

**问题**：
- 网格线计数误差 ±1~2 行/列，导致所有棋子坐标系统性偏移
- 无法精确定位棋子到正确的交叉点
- 部分棋盘（非 19×19 全图）让模型更难准确计数

#### 方法 2：纯 OpenCV 识别（当前实现，部分可用）

已实现 `scripts/recognize_boards_v2.py`：

**已验证有效的部分**：
- **网格线检测**（Step 2）：形态学操作 + 1D 投影 + peak finder → 精确到像素级，间距一致 (~39px)
- **缺失网格线插值**（gap-fill）：棋子遮断的网格线通过间距外推自动补全 → 所有图都稳定输出正确的行列数
- **黑棋检测**：dark_ratio > 0.45 → 准确率高
- **无数字白棋检测**：circ_contrast < -15（中心亮、边缘暗的圆环特征）→ 有效
- **带数字白棋检测**：dark_ratio > 0.28 AND std > 105 → 大部分有效

**已验证的参考数据**（图4，8 颗棋子全部正确）：
```
Expected: B(2,4)(3,9)(3,15)(4,3)(5,3) W(3,2)(4,2)(6,2) — PERFECT MATCH ✅
```

**当前问题**：
1. **白棋误分类为黑棋**：白棋上的深色数字（如白8）使 dark_ratio 过高，被判为黑棋
2. **无法识别落子序号**：当前只输出 `(col, row, B/W)`，不读数字
3. **无法识别三角、字母标注**：完全缺失
4. **区域映射不稳定**：部分图检测到 17-18 行而非 19 行，col_start/row_start 需要校准

### 现有代码资产

| 文件 | 内容 | 状态 |
|------|------|------|
| `scripts/recognize_boards_v2.py` | CV 流水线主脚本 | 已实现 grid detection + stone detection |
| `cv_detect_grid()` | 网格线检测（含 gap-fill） | ✅ 生产可用 |
| `cv_detect_stones()` | 棋子检测（基于阈值分类） | ⚠️ 需要重构为 occupied 检测 |
| `cv_detect_diagram_bboxes()` | 页面级棋图定位（CV 投影分析） | ✅ 基本可用 |
| `build_contact_sheet()` | contact sheet 拼图 | 尚未实现 |
| `classification_to_payload()` | VLLM 分类结果 → board_payload | 尚未实现 |

---

## 实施计划概要

### 核心架构：CV 定位 + VLLM 分类

**设计原则**：CV 负责精确定位（WHERE），VLLM 负责分类识别（WHAT）。

```
Page Image
  │
  ├── CV Pipeline (本地，毫秒级)
  │     ├─ 检测棋图 bbox + 裁剪
  │     ├─ 检测网格线（已实现）
  │     ├─ 检测所有 occupied 交叉点（宽松检测，不分类）
  │     └─ 裁剪每个交叉点 → 50×50 px 小图
  │
  ├── Contact Sheet（本地，毫秒级）
  │     └─ 所有小图拼成一张大图，标注位置编号
  │
  ├── VLLM 分类（每图一次调用）
  │     └─ 看 contact sheet → 分类每个小图
  │          → black / white / black+N / white+N / triangle / letter / empty
  │
  └── 组合 → board_payload → 写入 DB
```

### Phase 1：CV + VLLM Contact Sheet（近期实施）

1. **`cv_detect_occupied()`** 替代 `cv_detect_stones()`：
   - 使用多维特征（dark_ratio, edge_ratio, std_dev, circ_contrast）
   - 任一特征异常即标记为 occupied（宁多不漏）
   - 不做黑白分类，只检测"有东西"

2. **`build_contact_sheet()`**：
   - 将所有 occupied 交叉点裁剪拼成标注大图
   - 标签如 A:(3,2), B:(4,3) 便于 VLLM 引用

3. **VLLM 分类**（via subagent，Claude Max 会员）：
   - 一次调用处理一个 figure 的所有交叉点
   - 比之前的 subagent 方式快得多：只需看一张简单拼图，不需分析整页

4. **星位校准** `cv_detect_star_points()`：
   - 检测棋盘上的星位小圆点
   - 与已知 19×19 星位坐标匹配 → 确定 col_start/row_start

5. **自动保存训练数据**：
   - 每次处理时将标注后的裁剪小图按类别存入 `data/training_patches/`
   - 为 Phase 2 的模型训练积累数据

### Phase 2：EfficientNet-B0 轻量分类器（后续实施）

- 使用 Phase 1 积累的 ~2000 标注样本训练
- EfficientNet-B0（ImageNet 预训练）+ 分类头（8 类）+ 数字识别头（0-99）
- 替代 VLLM 实现离线快速推理（10-20ms/patch vs 10s/subagent call）

### Phase 3：主动学习与持续改进

- 模型低置信度时 fallback 到 VLLM 复核
- 跨书泛化测试（不同出版社、扫描质量）
- 数字识别专项优化（Tesseract / CRNN）

---

## 审核要求

请逐条回答以下问题，给出"通过 ✅ / 有问题 ❌ / 建议改进 ⚠️"的判定，并附上理由。

### 一、架构合理性

1. "CV 定位 + VLLM 分类"的职责分离是否合理？是否有更好的分工方式？
2. Contact sheet 方式是否是将多个小图批量发给 VLLM 的最优方案？是否应该考虑其他批量策略（如 JSON base64 编码、多图 API 调用等）？
3. CV 的 `occupied` 检测采用"宽松检测"策略（宁多不漏），VLLM 端用 `empty` 类别过滤假阳性——这种分工是否合理？漏检风险是否被充分控制？
4. 星位校准方案（`cv_detect_star_points` + 匹配已知坐标）是否足够鲁棒？如果棋子恰好落在星位上怎么办？

### 二、CV 技术方案

5. 网格线检测（形态学 + 1D 投影 + gap-fill）：gap-fill 的触发条件（gap > 1.6× spacing）是否可能误触发？例如棋盘边缘或特殊布局。
6. Occupied 检测的多维特征阈值（dark_ratio, edge_ratio, std_dev, circ_contrast）：这些阈值是基于一本书校准的，跨书泛化能力如何？是否需要自适应阈值？
7. 裁剪尺寸 50×50 px 是否足够 VLLM 分辨不同类别（尤其是数字 OCR）？是否需要更大的裁剪或图像增强（upscale、对比度增强）？
8. 棋图 bbox 检测使用 CV 投影分析，是否足够鲁棒？是否有必要用 VLLM 画 bbox 作为备选？

### 三、VLLM 分类方案

9. 分类类别设计（8 类：empty/black/white/black+N/white+N/triangle_black/triangle_white/letter）是否完备？是否有遗漏的标注类型（如方形标记 □、圆形标记 ○、数字标注在空交叉点上等）？
10. VLLM 通过 subagent 调用的效率问题：一个 figure 约 5-20 个 occupied 交叉点，一次 subagent 调用约 10-20 秒。一本书 200+ 个 figures，总时间是否可接受？有无加速方案？
11. VLLM 分类中的数字 OCR（读取棋子上的编号 1-99）：在 contact sheet 中 40×40 px 的小图上，VLLM 能否准确读取两位数数字？是否需要预处理？

### 四、Phase 2 模型训练

12. EfficientNet-B0 是否是最优的小模型选择？是否考虑过 MobileNetV3、ResNet18、或 ViT-Tiny？
13. 数据需求估算（~2000 样本 = ~2-3 本书）是否合理？类别不平衡问题如何处理（empty 远多于其他类别）？
14. 分类头（8 类）+ 数字识别头（0-99）的双头设计是否合理？数字识别是否应该作为独立模型？
15. 训练数据来自 VLLM 标注，如果 VLLM 本身有标注错误，如何防止错误传播到训练集？

### 五、工程实现

16. `recognize_boards_v2.py` 作为单文件脚本是否会过于臃肿？是否应该拆分为模块（`cv_pipeline.py`, `vllm_classifier.py`, `payload_builder.py`）？
17. 自动保存训练数据到 `data/training_patches/` 的目录结构设计是否合理？是否需要元数据文件（CSV/JSON）记录每个 patch 的来源信息？
18. 错误处理策略：如果某个 figure 的 VLLM 分类失败，应该跳过该 figure、使用 CV fallback、还是中断整个流程？
19. 处理一本新书的端到端流程是否足够清晰？操作者（可能是非技术人员）需要几步操作？

### 六、与 Stage 2 的集成

20. Stage 2 的 `update_figure_board()` API 带有乐观锁（optimistic locking via `updated_at`）。批量写入时是否会触发 409 冲突？
21. 识别结果写入 DB 后，viewport 由服务端自动计算。识别结果中是否需要包含 highlights 字段？当前固定为空数组是否正确？
22. 识别结果写入后，用户可以在前端编辑器中修正。修正后的数据是否应该反哺训练集？如何实现？

---

## 附：关键技术决策备选方案（供审核参考）

| 决策点 | 当前选择 | 备选方案 |
|--------|---------|---------|
| 分类器 | VLLM (Phase 1) → EfficientNet (Phase 2) | CLIP 零样本分类 / YOLO11 检测 / HOG+SVM |
| 数字 OCR | VLLM 在 contact sheet 中读取 | Tesseract (PSM=8) / PaddleOCR / 模板匹配 |
| VLLM 调用方式 | Subagent (Claude Max) | Anthropic SDK / Gemini Flash API / 本地 Qwen-VL |
| 棋图 bbox | CV 投影分析 | VLLM 画框 / YOLO 检测 |
| 区域校准 | 星位匹配 | VLLM 判断 / 棋盘边缘检测 |
| 训练数据来源 | VLLM 自动标注 | 人工标注 / 半监督学习 |

---

## 参考文件

- 实施计划全文：`superpowers/tracks/tutorial-module-stage3/2026-03-27-board-recognition-plan.md`
- Stage 2 计划（前置依赖）：`superpowers/archive/tutorial-module-stage2/2026-03-23-tutorial-v2-plan.md`
- 现有 CV 脚本：`scripts/recognize_boards_v2.py`
- 视觉识别前期调研：`superpowers/tracks/visual-recognition/plan.md`
