## Review Summary

这份设计文档结构清晰、逻辑严密，非常精准地响应了用户的硬性约束（特别是离线生成、版权隔离和纯展示的线上应用），整体成熟度很高。架构的分层很好地规避了线上系统的复杂度，只需补充少数边界细节即可进入 Implementation Planning。

## Blocking Issues

- `None` (没有会直接阻断进入实现计划的致命缺陷。)

## Risks and Gaps

1. **持久化 ID 稳定性 (ID Stability)**
   离线 Builder 每次重新运行或者导入新书增量构建时，生成的 `topic_id` 和 `example_id` 必须保持绝对稳定。如果 ID 发生变化，线上数据库记录的 `UserProgress` 就会失效或错乱。设计中尚未提及如何在离线层维护 Source -> Public ID 的稳定映射（如基于特征的 Deterministic Hash 或是持久化的 Mapping 记录）。
2. **截图视觉版权风险 (Screenshot Copyright Risk)**
   设计中对文本的版权隔离做得很彻底，但 Phase 1 沿用“书本截图”依然存在视觉特征泄露的风险。原书截图可能包含特有的棋盘样式、专属的字体排版、页码边缘残留或潜在的水印。如果直接暴露，仍可能被有心人识别出原书。
3. **内容相似度的自动化校验 (Similarity Check gap)**
   “避免照搬原文”目前完全依赖人工审核（Review workflow）。人工判断会有疲劳和主观误差。建议在自动化构建阶段加入机制保证底线安全。
4. **NLP 模块的工程不可控性 (LLM/NLP unpredictability)**
   “Topic 归并去重”和“文本转口播稿”高度依赖算法或 LLM。这部分如果预期的智能化过高，在实施时很容易失控，导致 Review 阶段的打回率极高，成为阻碍内容上线的瓶颈。

## Over-Engineering Check

- **可能过度设计的地方:** 
  对于 Phase 1 而言，“全自动的跨书 Topic 去重和归并”如果在初期只处理 1-2 本样板书，可能会花费大量时间调优算法但收效甚微。建议在 Phase 1 的实现中，这部分允许“基于配置表的半手动映射”或优先选择内容不重叠的书籍作为启动资源，避免在算法上陷入泥潭。
- **合理预留的地方:** 
  `Step` 对象中的 `board_mode: image | sgf` 是非常聪明的适度设计，既满足了 Phase 1 的低成本（使用现有截图）启动，又锁定了前端组件和数据契约的演进方向，避免了未来支持 SGF 时的伤筋动骨。三层架构（Private / Build / Public）严格区分内部资产与发布资产，对版权保护和安全来说是完全必要的。

## Recommended Adjustments

1. **Editorial build layer:**
   - 增加一个 **Similarity Check** 步骤：在 `rewrite` 后，计算 `narration_final` 与 `raw_text` 的相似度（如编辑距离或语义相似度），如果重合度过高直接拒绝进入 Draft，要求重新生成。
   - 增加一个 **Image Cropping/Sanitization** 环节：在处理截图时，通过自动化脚本尽量裁切掉棋盘外多余的白边、页眉页脚，减少视觉特征泄露。
2. **数据模型 (Data Model):**
   - 在 `Step` 数据对象中，建议补充 `audio_duration_ms`（音频时长）字段。前端拿到带有明确时长的 Step 列表，可以更好地渲染进度条和预测加载，而不需要等音频真正加载后才拿到时长。
   - 在 `DraftTopic` / `DraftExample` 模型中，明确引入持久化的 `stable_id` 机制。
3. **前端体验 (Frontend UX):**
   - 在 UX Shape 中补充关于“Step 间自动连播”与“自动提交进度”的定义：当前 Step 音频播放完毕后，是否自动进入下一 Step？这决定了调用 `POST /api/v1/tutorials/progress/{example_id}` 的时机和频率（是每个 Step 播完存一次，还是退出/完成整个 Example 存一次）。

## Verdict

- Ready for implementation planning