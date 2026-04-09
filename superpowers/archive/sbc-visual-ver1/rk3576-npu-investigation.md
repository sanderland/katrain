# RK3576 RKNPU 驱动调研报告

> **调研日期:** 2026-04-07
> **硬件:** KICKPI K7C (RK3576, 6 TOPS NPU)
> **目标:** 在 RK3576 上使用 rknn-toolkit-lite2 运行 YOLO v11 棋子检测模型

---

## 1. 硬件诊断结果

| 项目 | 结果 | 说明 |
|------|------|------|
| 芯片 | RK3576 | `rockchip,rk3576-evb1-v10` |
| 内核版本 | 6.1.75 | Rockchip BSP 内核 |
| NPU 硬件 | 存在 | `27700000.npu` (devfreq + platform device) |
| NPU 平台设备 | `rknpu_dev.9.auto` | 设备树已声明 |
| `/dev/rknpu` | **不存在** | 新架构设备节点缺失 |
| `/dev/dri/` | card0, card1, renderD128, renderD129 | NPU 通过 DRI 暴露（旧模式） |
| 驱动编译方式 | 内置 (`CONFIG_ROCKCHIP_RKNPU=y`) | 非可加载模块，无法单独替换 .ko |
| `dmesg \| grep rknpu` | 无输出 | 驱动静默加载，无版本日志 |

### 内核 RKNPU 配置

```
CONFIG_ROCKCHIP_RKNPU=y              # 驱动编译进内核
CONFIG_ROCKCHIP_RKNPU_DEBUG_FS=y     # debugfs 支持
CONFIG_ROCKCHIP_RKNPU_DRM_GEM=y      # ❌ 旧 DRM GEM 模式
# CONFIG_ROCKCHIP_RKNPU_PROC_FS is not set
# CONFIG_ROCKCHIP_RKNPU_FENCE is not set
# CONFIG_ROCKCHIP_RKNPU_SRAM is not set
```

---

## 2. ~~根本问题~~ → 结论修正：NPU 在 DRM_GEM 模式下已可用

> **⚠️ 2026-04-07 实测推翻了原结论。** 原文保留并标注删除线以记录调研过程。

~~**`CONFIG_ROCKCHIP_RKNPU_DRM_GEM=y`** 是问题根因。~~

Rockchip RKNPU 驱动有两种架构：

| 架构 | 设备节点 | 用户态接口 | librknnrt.so 2.0.0b0 兼容 |
|------|---------|-----------|----------------------|
| **新架构 (DMA_HEAP)** | `/dev/rknpu` | 专用 ioctl | ✅ 兼容 |
| **旧架构 (DRM GEM)** | `/dev/dri/renderDxxx` | DRM subsystem | ✅ **兼容（自动回退）** |

### 实测验证（2026-04-07）

```
$ rknn_common_test /usr/share/model/RK3576/mobilenet_v1.rknn /tmp/test_224.jpg
rknn_api/rknnrt version: 2.0.0b0 (35a6907d79@2024-03-24T10:31:14), driver version: 0.9.7
model input num: 1, output num: 1
...
Begin perf ...
   0: Elapse Time = 4.84ms, FPS = 206.83
---- Top5 ----
0.404785 - 412
0.211670 - 742
...
```

**MobileNetV1 推理成功，4.84ms / 206 FPS。NPU 完全可用。**

### `librknnrt.so` 双模式支持

`strings /usr/lib/librknnrt.so` 分析显示运行时库同时支持两种接口：

```
/dev/rknpu                    ← 优先尝试 DMA_HEAP 模式
renderD                       ← 回退到 DRM GEM 模式
/dev/dri/%s
%s/renderD%d
drmOpenByBusid: Interface 1.4 failed, trying 1.1
```

运行时版本 `2.0.0b0` 先尝试打开 `/dev/rknpu`，失败后自动回退到 `/dev/dri/renderD*` 的 DRM 路径。

### 原结论错误原因

原结论 "DRM_GEM 不兼容 rknn-toolkit-lite2" 可能基于较旧版本的 `librknnrt.so`（可能 < 2.0.0）。K7C 预装的 `librknnrt.so 2.0.0b0` 已经实现了 DRM 回退支持。

### 修正后的关键数据

| 项目 | 原记录 | 实测值 |
|------|--------|--------|
| RKNPU 驱动版本 | 0.9.8（厂商口头）| **0.9.7** |
| librknnrt.so 版本 | 未知 | **2.0.0b0** |
| DRM_GEM 兼容性 | ❌ 不兼容 | **✅ 兼容** |
| NPU 可用性 | 不可用 | **✅ 可用，4.84ms MobileNetV1** |
| 是否需要重编内核 | 需要 | **不需要** |

---

## 3. 厂商沟通记录

**厂商:** KICKPI (瑞芯微开发板淘宝技术支持 - 谢工)

**沟通时间:** 2026-03-30

**问:** K7C 上 RKNPU 驱动版本升级一般是跟着厂商的操作系统一起升级，还是自己可以找对应的开源库升级？

**答:** "目前已经是 0.9.8 了 kernel-6.1 的 可以单独升级"

**解读:**
- 厂商确认当前驱动版本为 v0.9.8（RKNPU 系列最新版本）
- "单独升级" 指可以自行从开源库获取驱动源码编译，不需要等厂商发布新系统镜像
- 但实际情况是驱动编译为 `=y`（内置），不是 `=m`（模块），单独替换需要重编内核或编译外部模块覆盖

---

## 4. 关键澄清：v0.9.8 版本号

之前 RK3562 调研中记录 "rknn-toolkit-lite2 需要 RKNPU 驱动 >= v1.4.0"，这个结论**需要修正**：

- v1.x 是旧一代 RKNPU 驱动（用于 RK3399Pro, RK1808 等老芯片）
- v0.9.x 是新一代 RKNPU 驱动（用于 RK3588, RK3576, RK3562 等新芯片）
- **v0.9.8 是当前最新版本**，RKNN SDK 和 RKLLM 都推荐此版本
- 问题不在版本号，而在**架构模式**（DRM GEM vs 专用设备节点）

---

## 5. 解决方案

### 方案 A：自行重编内核（可行但复杂，风险中）

从 Rockchip 开源仓库获取内核源码，修改配置后编译。

**内核源码仓库：**
- [rockchip-linux/kernel (develop-6.1)](https://github.com/rockchip-linux/kernel) — 官方 BSP
- [armbian/linux-rockchip (rk3576-6.1)](https://github.com/armbian/linux-rockchip/tree/rk3576-6.1-dev-2024_04_19) — Armbian 移植
- [friendlyarm/kernel-rockchip (nanopi6-v6.1.y)](https://github.com/friendlyarm/kernel-rockchip) — FriendlyARM 移植

**步骤：**
```bash
# 1. 克隆内核源码
git clone https://github.com/rockchip-linux/kernel -b develop-6.1

# 2. 导出当前内核配置
zcat /proc/config.gz > .config

# 3. 修改 RKNPU 配置
#    CONFIG_ROCKCHIP_RKNPU=y          (保持)
#    CONFIG_ROCKCHIP_RKNPU_DRM_GEM=n  (关掉旧模式 → 启用 /dev/rknpu)

# 4. 编译内核（本机或交叉编译）
make -j4 Image modules dtbs

# 5. 安装并重启
sudo make modules_install
sudo cp arch/arm64/boot/Image /boot/
sudo reboot
```

**风险：** 内核版本/设备树不匹配可能导致无法启动，需准备 SD 卡恢复手段。

### 方案 B：编译 RKNPU 为外部模块覆盖内置驱动（更安全，推荐）

不重编整个内核，只把 RKNPU 驱动编译为可加载模块 `.ko`，用 `insmod` 覆盖内置版本。

**前提条件：** 需要当前内核的 headers。

```bash
# 检查 headers 是否可用
ls /lib/modules/$(uname -r)/build/
dpkg -l | grep linux-headers
```

**相关工具/项目：**
- [rockchip-linux/rknpu](https://github.com/rockchip-linux/rknpu) — 官方驱动源码，含 Makefile
- [Pelochus/ezrknpu](https://github.com/Pelochus/ezrknpu) — 简化安装脚本
- [bmilde/rknpu-driver-dkms](https://github.com/bmilde/rknpu-driver-dkms) — RK3576 DKMS 支持（WIP，当前不能编译）

**注意：** 内置驱动 (`=y`) 会先于外部模块加载，可能需要在 initramfs 中 blacklist 或通过内核参数禁用内置驱动。

### 方案 C：要求厂商提供新内核镜像（最稳妥，推荐优先尝试）

将诊断结果发给 KICKPI 技术支持，要求提供关闭 `DRM_GEM` 的内核：

> 我们的 K7C 内核 6.1.75 使用 `CONFIG_ROCKCHIP_RKNPU_DRM_GEM=y`（旧 DRM GEM 模式），
> 没有 `/dev/rknpu` 设备节点。我们需要使用 `rknn-toolkit-lite2` 加载 RKNN 模型进行
> NPU 推理。能否提供关闭 DRM_GEM 模式的内核镜像（即 `CONFIG_ROCKCHIP_RKNPU_DRM_GEM=n`），
> 或提供完整的内核编译配置和设备树源码？

对厂商来说只需改一行配置重新编译。

---

## 6. NPU 启用后的预期收益

基于 RK3562 CPU 基准测试数据和 RK3576 NPU 规格（6 TOPS）的推算：

| 模型 | ONNX CPU (RK3576 估计) | RKNN NPU (RK3576 估计) | 加速比 |
|------|----------------------|----------------------|--------|
| yolo11n | ~400-600ms | ~40-100ms | 5-10x |
| yolo11s | ~1.0-1.5s | ~100-300ms | 5-7x |
| yolo11m | ~3-4s | ~300-800ms | 5-8x |

RK3576 的 NPU 算力 (6 TOPS) 远强于 RK3562 (1 TOPS)，启用后 yolo11n 有望实现 < 100ms 延迟，接近实时检测。

---

## 7. 模型转换流程（NPU 就绪后）

```
MacBook (x86)                         RK3576 (ARM64)
─────────────                         ──────────────
best.pt                               
  ↓ export_onnx.py                    
best.onnx + best.meta.json            
  ↓ rknn-toolkit2 (Docker/x86)        
best.rknn                             best.rknn
                                        ↓ rknn-toolkit-lite2
                                      NPU 推理
```

- **ONNX → RKNN 转换**必须在 x86 机器上完成（`rknn-toolkit2` 不支持 ARM）
- 转换时可选 INT8 量化（进一步加速，精度损失通常 < 2%）
- 转换脚本已规划在 `katrain/vision/tools/export_rknn.py`（待实现）

---

## 8. 当前决策（2026-04-07 更新）

| 决策 | 说明 |
|------|------|
| ~~短期：ONNX CPU 推理先行~~ | ~~使用 yolo11n ONNX 模型验证完整视觉流程~~ |
| **NPU 已可用，直接推进 RKNN 路线** | NPU 在 DRM_GEM 模式下已验证可用（4.84ms MobileNetV1） |
| **下一步：安装 rknn-toolkit-lite2** | 在 K7C 上安装 Python 包，用 Python API 验证推理 |
| **转换 YOLO 模型** | 在 Mac/x86 上用 rknn-toolkit2 将 yolo11n.onnx 转为 .rknn |
| **实现 RknnBackend** | 将 `rknn_backend.py` 从 stub 升级为完整实现 |
| ~~推进 NPU 驱动~~ | **不再需要** — 内核重编、厂商沟通均可跳过 |

---

## 9. 开源内核编译路线调研（2026-04-07 补充）

### 9.1 内核源码仓库评估

| 仓库 | 分支 | RK3576 支持 | RKNPU 默认 | 适用性 |
|------|------|------------|-----------|--------|
| [rockchip-linux/kernel](https://github.com/rockchip-linux/kernel) | `develop-6.1` | ✅ | `=y` (DRM_GEM) | 官方 BSP，最接近 K7C 原始内核 |
| [friendlyarm/kernel-rockchip](https://github.com/friendlyarm/kernel-rockchip) | `nanopi6-v6.1.y` | ✅ | `=m` (模块) | **已用模块模式**，构建工具链完善 |
| [armbian/linux-rockchip](https://github.com/armbian/linux-rockchip) | `rk3576-6.1-dev-2024_04_19` | ✅ | - | Armbian 移植，社区活跃 |

**KICKPI 不发布自己的内核仓库**，其 SDK 源码通过 OneDrive 下载，官方 wiki (`doc.kickpi.com`) SSL 证书已过期。

### 9.2 RKNPU 驱动源码分析

驱动位于 `drivers/rknpu/`，关键文件：

**`drivers/rknpu/Kconfig`** — 内存管理器为互斥选择：

```kconfig
choice
    prompt "RKNPU memory manager"
    default ROCKCHIP_RKNPU_DRM_GEM

config ROCKCHIP_RKNPU_DRM_GEM
    bool "RKNPU DRM GEM"
    depends on DRM

config ROCKCHIP_RKNPU_DMA_HEAP
    bool "RKNPU DMA heap"
    depends on DMABUF_HEAPS_ROCKCHIP_CMA_HEAP    # ← 关键依赖
endchoice
```

**`drivers/rknpu/rknpu_drv.c`** — 两种模式的探测路径完全不同：

| 模式 | 探测函数 | 创建设备 | ioctl 接口 |
|------|---------|---------|-----------|
| DRM_GEM | `rknpu_drm_probe()` → `drm_dev_alloc()` | `/dev/dri/renderDxxx` | `DRM_IOCTL_RKNPU_*` (via DRM subsystem) |
| DMA_HEAP | `misc_register(name="rknpu")` | `/dev/rknpu` | `IOCTL_RKNPU_*` (直接 ioctl, magic 'r') |

**切换仅需改一行配置**，无需修改设备树。NPU 设备树节点 (`rk3576.dtsi` 中 `0x27700000.npu`) 是模式无关的。

### 9.3 关键依赖验证

切换到 DMA_HEAP 模式前，必须确认 K7C 内核已启用：

```bash
# 在 K7C 上执行
zcat /proc/config.gz | grep DMABUF_HEAPS_ROCKCHIP
# 需要看到: CONFIG_DMABUF_HEAPS_ROCKCHIP_CMA_HEAP=y
```

如果未启用，则需要在重编内核时一并开启。

### 9.4 ⚠️ librknnrt.so 兼容性风险

**这是最关键的风险点。** `rknn-toolkit-lite2` 底层依赖闭源的 `librknnrt.so` 运行时库。该库通过 ioctl 与内核驱动通信：

- DRM_GEM 模式：通过 `/dev/dri/renderD*` + `DRM_IOCTL_RKNPU_*`
- DMA_HEAP 模式：通过 `/dev/rknpu` + `IOCTL_RKNPU_*`

**两种 ioctl 接口完全不同。** 必须确认 rknn-toolkit-lite2 附带的 `librknnrt.so` 版本支持 DMA_HEAP 模式（即 `/dev/rknpu` 路径）。如果它只支持 DRM 路径，则光改内核配置无用。

验证方法：
```bash
# 检查 librknnrt.so 是否引用 /dev/rknpu
strings /path/to/librknnrt.so | grep -E "rknpu|/dev/"
# 或检查 rknn-toolkit-lite2 文档中的驱动兼容性说明
```

### 9.5 方案 B 不可行性确认

**外部模块覆盖内置驱动（方案 B）已确认不可行：**

1. 内置驱动 (`=y`) 的代码直接链接进内核镜像，无法在运行时卸载
2. `modprobe.blacklist` 对内置驱动无效（只影响可加载模块）
3. 加载同名 `.ko` 会被拒绝（符号命名空间已被占用）
4. [bmilde/rknpu-driver-dkms](https://github.com/bmilde/rknpu-driver-dkms) 项目无法编译（缺少 Rockchip 内部头文件）
5. 唯一的外部模块方案仍需先重编内核设 `CONFIG_ROCKCHIP_RKNPU=n`，等于绕了一圈

### 9.6 推荐编译路线：FriendlyELEC 工具链

FriendlyELEC 的构建系统最成熟，且其 defconfig 已将 RKNPU 设为模块模式 (`=m`)。

#### 环境准备（x86 Linux，推荐 Ubuntu 20.04）

```bash
# 安装 FriendlyARM 交叉编译工具链
curl -fsSL https://raw.githubusercontent.com/friendlyarm/build-env-on-ubuntu-bionic/master/install.sh | sudo bash
# 工具链安装到 /opt/FriendlyARM/toolchain/11.3-aarch64/

# 或用 Docker（推荐 Mac 用户）
# FriendlyELEC 提供 docker-cross-compiler-novnc 容器
```

#### 编译步骤

```bash
# 1. 克隆内核
git clone https://github.com/friendlyarm/kernel-rockchip -b nanopi6-v6.1.y
cd kernel-rockchip

# 2. 设置工具链
export PATH=/opt/FriendlyARM/toolchain/11.3-aarch64/bin/:$PATH
export CROSS_COMPILE=aarch64-linux-gnu-
export ARCH=arm64

# 3. 加载基础配置（二选一）
#    方案一：用 FriendlyELEC defconfig（RKNPU 已是 =m）
make nanopi5_linux_defconfig
#    方案二：用 K7C 导出的配置（需先在板子上 zcat /proc/config.gz > k7c.config）
cp k7c.config .config

# 4. 进入菜单配置
make menuconfig
# 导航: Device Drivers → RKNPU
#   - 确认 CONFIG_ROCKCHIP_RKNPU=y 或 =m
#   - RKNPU memory manager → 选择 "RKNPU DMA heap"（而非 DRM GEM）
# 导航: Device Drivers → DMABUF options
#   - 确认 CONFIG_DMABUF_HEAPS_ROCKCHIP_CMA_HEAP=y

# 5. 编译
make -j$(nproc) Image modules dtbs

# 6. 打包（输出 kernel.img + resource.img）
# FriendlyELEC SDK 有专用打包脚本，或手动：
# - kernel.img = arch/arm64/boot/Image (可能需要 gzip 或 Android boot header 包装)
# - resource.img = DTB 打包（Rockchip 格式）
```

#### 已知编译问题

| 问题 | 解决 |
|------|------|
| `rockchip_drm_vop2.c` 未使用变量 `use_cluster` 编译错误 ([#359](https://github.com/rockchip-linux/kernel/issues/359)) | 删除或 `#ifdef` 该变量 |
| Panfrost GPU 驱动在 RK3576 上导致 kernel panic | 设 `CONFIG_DRM_PANFROST=n` |
| `CONFIG_MFD_RK806_I2C` 未启用导致 NPU 等设备探测失败 | 确保 `=y` |
| 不要以 root 用户编译 | 用普通用户 |

### 9.7 K7C 启动分区与刷写

KICKPI K7C 使用 **Rockchip GPT 分区布局**（非标准 /boot）：

```
分区 5: kernel    (37MB-79MB)   ← kernel.img
分区 4: resource  (20MB-37MB)   ← resource.img (含 DTB)
分区 8: rootfs    (147MB+, ext4)← /lib/modules/
```

刷写方式：

```bash
# 方式一：板载 dd（eMMC 为 /dev/mmcblk2）
dd if=kernel.img of=/dev/mmcblk2p5 bs=1M
dd if=resource.img of=/dev/mmcblk2p4 bs=1M
sync && reboot

# 方式二：USB 线刷（Rockchip upgrade_tool）
sudo upgrade_tool di -k kernel.img
sudo upgrade_tool di -re resource.img
sudo upgrade_tool RD
```

**⚠️ 务必先备份原始分区：**
```bash
dd if=/dev/mmcblk2p5 of=/backup/kernel.img.orig bs=1M
dd if=/dev/mmcblk2p4 of=/backup/resource.img.orig bs=1M
```

### 9.8 修订后的方案优先级

| 优先级 | 方案 | 风险 | 说明 |
|--------|------|------|------|
| **1** | **方案 C：要求 KICKPI 提供新内核** | 低 | 对厂商只是改一行配置，零风险 |
| **2** | **方案 A：自行编译内核** | 中 | 用 FriendlyELEC 工具链，路线已验证 |
| ~~3~~ | ~~方案 B：外部模块覆盖~~ | - | **已确认不可行，排除** |

**在动手编译之前，必须先验证 `librknnrt.so` 的 DMA_HEAP 兼容性**（见 9.4），否则编译出新内核也可能无法使用。

---

## 10. 待办事项（2026-04-07 更新）

- [x] 在 K7C 上验证 NPU 硬件可用性 — **已验证，4.84ms MobileNetV1**
- [x] 验证 `librknnrt.so` 兼容性 — **2.0.0b0，支持 DRM_GEM 回退**
- [x] `CONFIG_DMABUF_HEAPS_ROCKCHIP_CMA_HEAP` — 未启用，但**不影响**（DRM_GEM 模式可用）
- [ ] 在 K7C 上安装 `rknn-toolkit-lite2` Python 包
- [ ] 用 Python API (`rknn_lite.RKNNLite`) 验证推理流程
- [ ] 在 Mac/x86 上用 `rknn-toolkit2` 将 yolo11n.onnx 转换为 .rknn（`export_rknn.py`）
- [ ] 将 .rknn 模型部署到 K7C，测试 YOLO 棋子检测性能
- [ ] 完善 `rknn_backend.py`，从 stub 升级为完整实现
- ~~将诊断结果发给 KICKPI 厂商~~ — **不再需要**
- ~~搭建交叉编译环境~~ — **不再需要**
