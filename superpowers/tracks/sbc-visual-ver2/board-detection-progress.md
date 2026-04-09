# 棋盘与棋子视觉识别：问题总结与改进记录

> 更新日期：2026-04-08

## 一、项目背景

KaTrain 智能棋盘需要通过摄像头实时识别物理棋盘上的棋子位置，映射到 19×19 电子棋盘。整体 pipeline：

```
摄像头帧 → 运动过滤 → 棋盘边界检测 → 透视变换(warped) → YOLO棋子检测 → 坐标映射(19×19) → 电子棋盘
```

核心代码位置：`katrain/vision/`

## 二、遇到的问题

### 问题 1：Canny 边缘检测无法找到棋盘轮廓

**现象**：Board 耗时 8ms 但 YOLO 始终 0ms，棋盘未检测到。

**根因**：19 路围棋盘网格线太密集，Canny 将网格线全部检测为边缘，导致棋盘轮廓被切成碎片。最大轮廓仅占帧面积 22%（应为 ~40%），且 aspect ratio 异常。

**诊断依据**：在 Mac 上用真实摄像头帧运行 BoardFinder 并输出 Canny 边缘图和轮廓分析。

**相关代码**：`katrain/vision/board_finder.py` → `_detect_canny()`, `_try_canny_with_epsilon()`

### 问题 2：颜色分割检测到家具而非棋盘

**现象**：绿色四边形覆盖棋盘 + 左侧木质家具，aspect ratio 2.2（应为 ~1.0）。

**根因**：HSV 颜色阈值将所有暖色木头（包括家具）一起检测。棋盘和家具木色相近且物理相邻，形态学操作无法完全分离。

**解决**：通过分析棋盘 vs 家具的 HSV 数据，发现棋盘 V 中位数=211 vs 家具 V=118。将 V 下限从 80 提高到 140，成功分离。

**相关代码**：`katrain/vision/board_finder.py` → `_detect_by_color()`, HSV 阈值 `[10, 30, 140]~[40, 180, 255]`

### 问题 3：YOLO 预处理 squish 导致棋子检测率极低

**现象**：warped 图 400×257 被 squish 到 640×640，圆形棋子变成 1.56:1 椭圆，检测从 13 颗降到 2 颗。

**根因**：ONNX/RKNN backend 的 `_preprocess()` 直接 `cv2.resize(image, (size, size))`，不保持宽高比。

**相关代码**：`katrain/vision/inference/onnx_backend.py` → `_preprocess()`, `katrain/vision/inference/rknn_backend.py` → `_preprocess()`

### 问题 4：摄像头对焦模糊

**现象**：清晰帧检测 13 颗棋子，模糊帧仅 9 颗。白子漏检严重。

**根因**：摄像头打开后未等待自动对焦稳定（需 2-3 秒），立即开始读帧。

**相关代码**：`katrain/vision/camera.py` → `open()`

### 问题 5：电子棋盘上棋子位置飘忽不定（当前最大问题）

**现象**：棋子在相邻网格位置间来回跳动，所有棋子同时左右摇摆。

**根因**：颜色分割每帧产生略有不同的棋盘角点（HSV mask 受自动曝光影响），角点漂移导致透视变换矩阵帧间变化，进而导致所有棋子位置同步偏移。`allowed_moving_length=50` 容差太大（Fe-Fool 用 10）。

**相关代码**：`katrain/vision/board_finder.py` → 稳定性过滤器（`allowed_moving_length`），`katrain/vision/worker.py` → `_processing_loop()`

### 问题 6：摄像头/棋盘移动后检测卡死

**现象**：移动摄像头后绿色边框消失，不再重新检测。

**根因**：稳定性过滤器拒绝偏移 >10px 的帧，但**不更新基准**，导致系统永远卡在旧基准位置。锁定模式下更严重——直接复用旧的透视矩阵。

**相关代码**：`katrain/vision/board_finder.py` → 稳定性过滤器拒绝逻辑

## 三、已完成的改进

### 改进 1：HSV 颜色分割作为主检测方法

取代 Canny 作为首选棋盘检测方式。通过 HSV 色彩空间阈值提取木色棋盘区域，用形态学操作（open 断开家具连接，close 填充网格线间隙），最终 convex hull + approxPolyDP 拟合四边形。

- **检测优先级**：ArUco → 颜色分割 → Canny（兜底）
- **文件**：`katrain/vision/board_finder.py` → `_detect_by_color()`
- **效果**：从"完全找不到棋盘"到稳定检测，面积占比 ~31%

### 改进 2：Letterbox 预处理

替换 squish resize 为 letterbox（保持宽高比 + 灰色 padding），确保棋子保持圆形。

- **文件**：`katrain/vision/inference/base.py` → `letterbox_preprocess()`，`onnx_backend.py` 和 `rknn_backend.py` 的 `_preprocess()` + `_postprocess()` 坐标修正
- **效果**：检测从 2 颗 → 13 颗，置信度从 49% → 97%
- **测试**：`tests/test_vision/test_letterbox.py`

### 改进 3：摄像头对焦等待

打开摄像头后读帧 2 秒让自动对焦/曝光稳定。

- **文件**：`katrain/vision/camera.py` → `open()` warmup 逻辑，`katrain/vision/worker.py` → 配置传递
- **效果**：清晰帧白子检测从 0 → 6 颗

### 改进 4：Hough 网格标定模块

在 warped 图上用 HoughLinesP 检测 19×19 网格线，RANSAC 拟合等间距网格，计算精确的 border offset。开局时运行一次，缓存结果。

- **文件**：`katrain/vision/grid_calibrator.py` → `GridCalibrator`, `GridCalibration`, `pixel_to_grid_calibrated()`
- **测试**：`tests/test_vision/test_grid_calibrator.py`（17 个测试）
- **效果**：361 个交叉点精准对齐实际网格线

### 改进 5：角点稳定性收紧 + 棋盘锁定

- `allowed_moving_length` 从 50 降到 10（匹配 Fe-Fool）
- "确认"按钮锁定透视矩阵，后续帧不再重新检测棋盘
- 2 帧时序平滑：网格位置需连续 2 帧一致才更新电子棋盘

- **文件**：`katrain/vision/board_finder.py`，`katrain/vision/worker.py` → `_board_locked` + 时序平滑逻辑

### 改进 6：移动后自动恢复

- 拒绝帧时更新角点基准（Fe-Fool 模式），2 帧内自动恢复
- 锁定模式下连续 10 次检测失败自动解锁
- 前端添加"重新检测"按钮

- **文件**：`katrain/vision/board_finder.py`，`katrain/vision/worker.py`，`katrain/web/ui/src/kiosk/pages/VisionSetupPage.tsx`

### 改进 7：USB 摄像头重连 + 设备号变更处理

物理断开重连后 Linux 可能重新分配 `/dev/video` 编号。首次连接时通过 sysfs 记录设备名称，断线重连时扫描所有设备找到匹配项。

- **文件**：`katrain/vision/camera.py` → `_get_camera_name()`, `_find_device_by_name()`

### 改进 8：RKNN NPU 加速

从 ONNX CPU 推理（532ms）切换到 RKNN NPU 推理（80ms），运行时升级到 2.3.2。

- **文件**：`katrain/vision/inference/rknn_backend.py`
- **效果**：YOLO 延迟从 532ms → 80ms

## 四、当前最大瓶颈：棋盘边框检测稳定性

**核心问题**：颜色分割（`_detect_by_color`）本质上不稳定——HSV mask 随自动曝光帧间波动，导致角点每帧微动。所有上游的稳定化措施（角点容差、锁定、时序平滑）都是在**掩盖**这个根因，而非解决。

**表现**：
- 绿色四边形每帧微动（几像素到几十像素）
- 电子棋盘上所有棋子同步左右摇摆
- 锁定后稳定，但移动摄像头/棋盘后需要手动重新检测

**根因分析**：
1. 摄像头自动曝光导致每帧亮度微变 → HSV 阈值边界像素翻转 → mask 形状变化 → 轮廓角点变化
2. 凸包 + approxPolyDP 对轮廓形状敏感，微小 mask 变化可导致角点跳跃
3. 没有角点平滑/指数移动平均机制

**可选解决方案（按推荐程度排序）**：

| 方案 | 稳定性 | 工作量 | 侵入性 |
|------|--------|--------|--------|
| **ArUco 标记**（棋盘四角贴 4 个 2cm 标记） | 最高（亚像素精度，零漂移） | 低（代码已实现） | 需物理标记 |
| **角点指数移动平均**（EMA 平滑角点位置） | 高（消除帧间抖动） | 低 | 纯软件 |
| **棋盘确认后锁定 + 更智能的失效检测** | 中高 | 低 | 已部分实现 |
| **固定摄像头曝光**（关闭自动曝光） | 中 | 低 | 可能影响光照适应 |
| **基于网格线的精确标定**（Hough 后锁定网格） | 高 | 中 | 已有 GridCalibrator |

## 五、参考项目 Fe-Fool 的稳定化策略

来源：`/Users/fan/Repositories/Fe-Fool/code/robot/`

Fe-Fool 通过 4 层过滤而非平滑实现稳定：

1. **帧间运动检测**（`window_detection.py`）：max_diff > 120 拒绝帧
2. **角点 10px 容差**（`image_find_focus.py`）：角点偏移 >10px 拒绝，但**更新基准**
3. **YOLO 结果投票**（`window_detection.py`）：连续 2 帧类别列表一致才发布
4. **3 帧落子确认**（`robot_master.py`）：新棋子同位置出现 3 帧才确认

关键差异：Fe-Fool 用的是 13×13 五子棋盘，Canny 边缘检测能直接找到干净的棋盘轮廓。19×19 围棋盘网格太密，Canny 失效，被迫使用颜色分割——这是不稳定的根源。

## 六、关键文件索引

| 文件 | 职责 |
|------|------|
| `katrain/vision/board_finder.py` | 棋盘边界检测（ArUco / 颜色分割 / Canny） |
| `katrain/vision/worker.py` | 视觉处理主循环（帧读取 → 检测 → 状态发布） |
| `katrain/vision/camera.py` | 摄像头管理（线程读帧、重连、对焦等待） |
| `katrain/vision/stone_detector.py` | YOLO 棋子检测封装 |
| `katrain/vision/inference/base.py` | letterbox 预处理函数 |
| `katrain/vision/inference/onnx_backend.py` | ONNX 推理后端 |
| `katrain/vision/inference/rknn_backend.py` | RKNN NPU 推理后端 |
| `katrain/vision/grid_calibrator.py` | Hough 网格标定 |
| `katrain/vision/board_state.py` | YOLO 检测结果 → 19×19 网格坐标 |
| `katrain/vision/coordinates.py` | 像素↔物理↔网格坐标转换 |
| `katrain/vision/motion_filter.py` | 帧间运动过滤（跳过手部移动帧） |
| `katrain/vision/move_detector.py` | 多帧落子确认 |
| `katrain/vision/config.py` | BoardConfig 棋盘物理尺寸 |
| `katrain/vision/ipc.py` | 进程间通信协议（WorkerStatus, ConfirmedMove） |
| `katrain/vision/sync.py` | 状态同步机（calibrating → tracking → ...） |
| `katrain/web/api/v1/endpoints/vision.py` | REST API（stream, detected-board, pose-lock 等） |
| `katrain/web/ui/src/kiosk/pages/VisionSetupPage.tsx` | 前端：摄像头 + 电子棋盘页面 |
| `katrain/web/ui/src/kiosk/components/vision/VisionBoard.tsx` | 前端：19×19 棋盘 Canvas 渲染组件 |
| `tests/test_vision/` | 视觉模块测试（138 个） |
