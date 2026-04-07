# Stage 3 Review Assessment — Gemini & Codex Feedback

## 综合评价

两份审核质量都很高。Codex 更偏工程精确性（发现了 DB 直写绕过 viewport 计算、empty 类样本遗漏、0-99 数字头与需求不匹配等具体 bug），Gemini 更偏架构层面（自适应阈值、Focal Loss、用户修正反哺表设计）。两者互补，综合采纳。

## 双方一致的关键问题（必须修改）

| # | 问题 | Gemini | Codex | 处理 |
|---|------|--------|-------|------|
| 4 | 星位校准不够鲁棒 | ❌ | ❌ | 改为多证据假设搜索（边框+星位+行列数） |
| 9 | 分类类别不完备 | ❌ | ❌ | 增加 `unknown`、`square`、`circle`；拆成 `base_type` + `attributes` |
| 16 | 单文件脚本过大 | ❌ | ⚠️ | 立即拆分为模块 |
| 15 | VLLM 标注错误传播 | ⚠️ | ❌ | 三层数据集（raw_auto → reviewed → gold）+ manifest.jsonl |
| 13 | empty 类样本遗漏 | — | ❌ | 修复 save_training_patches()，保存 empty 样本 |

## 有价值的独立建议

### Gemini 独有

| 建议 | 采纳 | 理由 |
|------|------|------|
| CV 先处理高置信度黑白子，只把低置信度送 VLLM | ✅ 采纳 | 大幅减少 VLLM 调用量，加速处理 |
| 对 patch 做 CLAHE 对比度增强 | ✅ 采纳 | 成本极低，提升 OCR 准确率 |
| Focal Loss 处理类别不平衡 | ✅ 采纳 Phase 2 | 训练时使用 |
| `recognition_corrections` 修正表 | ✅ 采纳 Phase 2 | 用户修正闭环 |
| asyncio 并发 API 调用 | ⏸ 暂缓 | Phase 1 用 subagent 即可，Phase 2 训练模型后不再需要 |

### Codex 独有

| 建议 | 采纳 | 理由 |
|------|------|------|
| DB 直写绕过了 compute_viewport() | ✅ 立即修复 | 真实 bug，前端会回退全盘显示 |
| 数字头改为序列模型（支持 100+） | ✅ 采纳 | 需求是 1-99+，100-class 不够 |
| per-figure 状态：success/needs_review/failed | ✅ 采纳 | 健壮的批处理必需 |
| 验收指标量化 | ✅ 采纳 | grid exact-match, occupied recall, B/W accuracy 等 |
| 数字 OCR 与分类分开做 | ✅ 采纳 | 裁剪尺寸和预处理需求不同 |
| manifest.jsonl 完整 provenance | ✅ 采纳 | 可追溯、可复现 |
| 封装成 CLI 任务流 | ✅ 采纳 Phase 1.5 | prepare → classify → review → apply → report |

### 双方分歧

| 问题 | Gemini | Codex | 决定 |
|------|--------|-------|------|
| 数字 OCR 在 contact sheet 上可靠吗 | ✅ 可靠 | ❌ 不可靠 | **采纳 Codex**：分开处理更安全，放大裁剪专用于 OCR |
| 乐观锁 409 是否会触发 | ✅ 不会 | ❌ 问题在别处（脚本不走 API） | **采纳 Codex**：问题本质是脚本绕过了 API 层 |

## 不采纳的建议

| 建议 | 来源 | 不采纳理由 |
|------|------|-----------|
| Contact sheet 改为 SDK 多图调用 | Codex | Phase 1 用 subagent，contact sheet 对人工 QA 也有价值 |
| 立即做 3 种骨干网络 baseline | Codex | Phase 2 的事，Phase 1 先积累数据 |
| ViT-Tiny | Codex 提及 | 数据量不够，不划算 |
