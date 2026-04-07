# RKNN 模型转换实战记录

> **日期:** 2026-04-07
> **硬件:** KICKPI K7C (RK3576, 6 TOPS NPU)
> **目标:** 将 YOLO v11 棋子检测模型从 ONNX 转换为 RKNN 格式，在 NPU 上运行推理

---

## 1. 背景

在 [rk3576-npu-investigation.md](rk3576-npu-investigation.md) 中，我们原本认为 K7C 的 NPU
因 `CONFIG_ROCKCHIP_RKNPU_DRM_GEM=y` 内核配置而无法使用。经过实测验证，发现
**`librknnrt.so 2.0.0b0` 支持 DRM GEM 回退**，NPU 在当前内核下完全可用
（MobileNetV1 推理 4.84ms / 206 FPS）。

这意味着不需要重编内核，可以直接推进模型转换和部署。

---

## 2. 转换流程总览

```
MacBook (Apple Silicon)              KICKPI K7C (RK3576 ARM64)
───────────────────────              ─────────────────────────
best.pt
  ↓ export_onnx.py (ultralytics)
best.onnx + best.meta.json
  ↓ export_rknn.py (Docker x86 容器)
best_rk3576.rknn + best_rk3576.meta.json  →  scp  →  best_rk3576.rknn
                                                        ↓ RknnBackend
                                                      NPU 推理
```

**关键约束：** `rknn-toolkit2`（转换工具）仅支持 x86 Linux，不能在 macOS 或 ARM 上运行。
在 Apple Silicon Mac 上必须通过 Docker + QEMU x86 模拟执行。

---

## 3. Docker 环境搭建过程

### 3.1 初始尝试：直接 pip install

```bash
pip install rknn-toolkit2  # Apple Silicon Mac
# ERROR: No matching distribution found — 仅有 x86 Linux wheels
```

结论：必须用 Docker。

### 3.2 Dockerfile 迭代

#### 第一版：基础镜像 + 依赖

```dockerfile
FROM python:3.10-slim
RUN apt-get update && apt-get install -y libgl1-mesa-glx libglib2.0-0
RUN pip install rknn-toolkit2==2.0.0b0 numpy opencv-python-headless
```

**问题 1：** `libgl1-mesa-glx` 在 Debian Trixie 中已移除。
**修复：** 删除该包，`opencv-python-headless` 不需要 OpenGL。

**问题 2：** `rknn-toolkit2==2.0.0b0` 不在 PyPI 上（可用版本：2.2.0, 2.3.0, 2.3.2）。
**决策：** 使用最新 2.3.2，后续验证模型兼容性。

#### 第二版：解决 CUDA 依赖膨胀

直接 `pip install rknn-toolkit2` 会通过 onnxruntime 拉入 CUDA 依赖（nvidia-cudnn-cu12
等），总计约 2GB，转换模型完全不需要 GPU。

**解决方案：** 先装 CPU 版 onnxruntime，再用 `--no-deps` 装 rknn-toolkit2。

```dockerfile
RUN pip install onnxruntime  # CPU 版，抢占 onnxruntime 命名空间
RUN pip install --no-deps rknn-toolkit2  # 跳过依赖解析，避免 CUDA
```

**问题 3：** `from rknn.api import RKNN` 报 `No module named 'torch'`。
rknn-toolkit2 在导入时就强制检查 torch，即使转换 ONNX 模型不需要 PyTorch。

**修复：** 单独安装 torch CPU 版（需要独立的 `--index-url`）：

```dockerfile
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
```

**注意：** `--index-url` 是全局生效的，不能和其他 PyPI 包放在同一个 `pip install` 中，
否则 protobuf 等包会找不到。必须分成两条 RUN 指令。

#### 第三版：onnx 版本兼容

**问题 4：** `onnx 1.21.0` 删除了 `onnx.mapping` 模块，rknn-toolkit2 2.3.2 内部依赖该模块。

```
AttributeError: module 'onnx' has no attribute 'mapping'
```

**修复：** 固定 onnx 版本 `>=1.16.1,<1.17`。

#### 第四版：PYTHONPATH

**问题 5：** 容器内 `python -m katrain.vision.tools.export_rknn` 找不到 `katrain` 模块。

**修复：** Dockerfile 添加 `ENV PYTHONPATH=/work`，`/work` 为项目挂载点。

### 3.3 最终 Dockerfile

```dockerfile
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    "numpy<=1.26.4" \
    "protobuf<=4.25.4,>=4.21.6" \
    opencv-python-headless \
    onnxruntime \
    "onnx>=1.16.1,<1.17" \
    "psutil>=5.9.0" \
    "scipy>=1.9.3" \
    "tqdm>=4.64.1" \
    ruamel.yaml \
    fast-histogram \
    && pip install --no-cache-dir --no-deps rknn-toolkit2

WORKDIR /work
ENV PYTHONPATH=/work

ENTRYPOINT ["python", "-m", "katrain.vision.tools.export_rknn"]
```

位于 `katrain/vision/tools/Dockerfile.rknn`。

---

## 4. ONNX Opset 兼容问题

转换执行后遇到：

```
ValueError: Unsupport onnx opset 20, need <= 19!
```

我们的 YOLO v11 模型导出时使用了 ONNX opset 20，但 rknn-toolkit2 2.3.2 仅支持 <= 19。

**解决方案：** 在 `export_rknn.py` 中自动检测并降级 opset：

```python
import onnx
from onnx import version_converter

model = onnx.load(onnx_path)
if model.opset_import[0].version > 19:
    converted = version_converter.convert_version(model, 19)
    onnx.save(converted, tmp_path)
```

降级后的临时文件 `best_opset19.onnx` 仅用于转换过程，不影响原始 ONNX 模型。

---

## 5. 模型归一化策略

ONNX 模型期望 float32 [0,1] 归一化输入。RKNN 转换时通过 `config()` 将归一化烘焙进模型：

```python
rknn.config(
    mean_values=[[0, 0, 0]],
    std_values=[[255, 255, 255]],  # 等效于 /255.0
    target_platform='rk3576',
)
```

这样 RknnBackend 在推理时只需喂 uint8 NHWC 图像，无需做浮点归一化，减少 ARM CPU 开销。

| 属性 | ONNX | RKNN |
|------|------|------|
| 输入布局 | NCHW float32 | NHWC uint8 |
| 归一化 | 推理时在 CPU 上做 | 烘焙进模型，NPU 内部处理 |
| 输出格式 | `(1, 6, 8400)` yolo_v8_raw | 同 ONNX |

---

## 6. 转换结果

全部 12 个 YOLO v11 模型转换成功（4 种架构 × 3 种分辨率）：

| 模型 | 640 | 960 | 1280 |
|------|-----|-----|------|
| yolo11n | 13M | 25M | 57M |
| yolo11s | 27M | 40M | 74M |
| yolo11m | 49M | 64M | 101M |
| yolo11x | 125M | 143M | 187M |

每个 `.rknn` 文件旁边都有对应的 `.meta.json` 元数据文件，供 `RknnBackend` 读取。

---

## 7. 版本兼容性风险

| 组件 | 版本 | 说明 |
|------|------|------|
| librknnrt.so (K7C) | 2.0.0b0 | 板载运行时 |
| rknn-toolkit2 (转换) | 2.3.2 | Docker 中的转换工具 |
| rknn-toolkit-lite2 (K7C) | 2.0.0b0 | Python API |
| RKNPU 驱动 (K7C) | 0.9.7 | 内核驱动 |

转换工具 (2.3.2) 和运行时 (2.0.0b0) 版本不一致。RKNN 模型文件有内部版本号，
如果运行时不支持新版本格式，加载时会报错：

```
RKNN Model version: X.X.X not match with rknn runtime version: Y.Y.Y
```

如遇此问题，需改用 2.0.0b0 版本的 rknn-toolkit2（从 GitHub v2.0.0-beta0 tag 获取 wheel）。

---

## 8. 使用方式

### 转换单个模型

```bash
./katrain/vision/tools/convert_rknn.sh --onnx katrain/vision/models/yolo11n/best.onnx --target rk3576
```

### 带 INT8 量化（需校准数据集）

```bash
./katrain/vision/tools/convert_rknn.sh \
  --onnx katrain/vision/models/yolo11n/best.onnx \
  --target rk3576 \
  --quantize --dataset calibration.txt
```

### K7C 上推理测试

```python
from rknnlite.api import RKNNLite
import numpy as np

rknn = RKNNLite()
rknn.load_rknn('best_rk3576.rknn')
rknn.init_runtime()

img = np.random.randint(0, 255, (1, 640, 640, 3), dtype=np.uint8)
outputs = rknn.inference(inputs=[img])
print('Output shape:', outputs[0].shape)  # (1, 6, 8400)
rknn.release()
```

---

## 9. 关键文件

| 文件 | 用途 |
|------|------|
| `katrain/vision/tools/export_rknn.py` | ONNX → RKNN 转换脚本 |
| `katrain/vision/tools/Dockerfile.rknn` | Docker 镜像定义 |
| `katrain/vision/tools/convert_rknn.sh` | 转换便捷脚本 |
| `katrain/vision/inference/rknn_backend.py` | NPU 推理后端 |
| `katrain/vision/models/yolo11*/best_rk3576.rknn` | 转换后的模型 |
| `katrain/vision/models/yolo11*/best_rk3576.meta.json` | 模型元数据 |

---

## 10. 踩坑总结

| 问题 | 原因 | 解决 |
|------|------|------|
| macOS 无法安装 rknn-toolkit2 | 仅有 x86 Linux wheels | Docker `--platform linux/amd64` |
| libgl1-mesa-glx 安装失败 | Debian Trixie 移除该包 | 使用 opencv-python-headless |
| rknn-toolkit2 2.0.0b0 不在 PyPI | 仅 2.2.0+ 在 PyPI | 使用 2.3.2 |
| 拉入 2GB CUDA 依赖 | onnxruntime 默认装 CUDA 版 | 先装 CPU 版再 `--no-deps` |
| `No module named 'torch'` | rknn-toolkit2 导入时检查 torch | 单独安装 torch CPU |
| `--index-url` 污染全部包 | pip 全局应用 index URL | 分离 RUN 指令 |
| `onnx.mapping` 不存在 | onnx 1.21 删除该模块 | 固定 `onnx>=1.16.1,<1.17` |
| PYTHONPATH 缺失 | 容器内找不到 katrain 模块 | `ENV PYTHONPATH=/work` |
| ONNX opset 20 不支持 | rknn-toolkit2 仅支持 <= 19 | 自动 opset 降级至 19 |

---

## 11. 下一步

- [ ] 将 `.rknn` 模型部署到 K7C，测试推理速度
- [ ] 验证 rknn-toolkit2 2.3.2 生成的模型能否被 librknnrt.so 2.0.0b0 加载
- [ ] 如版本不兼容，改用 GitHub v2.0.0-beta0 wheel 重新转换
- [ ] 用真实棋盘图片端到端测试 RknnBackend 检测精度
- [ ] 评估 INT8 量化对精度和速度的影响
