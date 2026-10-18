# ColorFlow v3 · 达芬奇调色助手

当前版本：**1.2.0**（2026-10-18） · 更新记录：[CHANGELOG.md](CHANGELOG.md)

按“先看懂素材、再做技术归一、再做参考匹配、最后批量和 QC”的思路重构的 DaVinci Resolve Studio 面板。界面使用扁平单列布局，并带真实缩略图预览。

1. **素材分析**：分辨率、帧率、编码、位深、元数据白平衡、Log 识别，以及高光/暗部/色域风险提示。
2. **一级调色**：DRX 节点树模板、自动黑白场、自动白平衡、自动曝光拉伸、LUT 套用与移除。
3. **镜头匹配与肤色**：参考帧锁定、统计匹配、YCbCr 肤色限定 DCTL、肤色微调与背景降饱和。
4. **预设与批量**：保存当前节点链为 DRX 预设、分类/收藏/删除、批量套用、整条时间线校验并输出 HTML 报告。

界面包含当前镜头、参考镜头、目标镜头和结果预览；主动画预览来自时间线播放头当前帧。
右上角可切换“中文 / English”：页签、按钮、标题、上下文、预览信息和主要警告会同步切换。

完整使用说明书：[USER_GUIDE.md](USER_GUIDE.md)

## 安装

需要 Windows + DaVinci Resolve Studio 21.x。

```powershell
Set-Location "D:\工作中工程\项目开发\达芬奇插件"
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

安装到：

```
%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Workflow Integration Plugins\
    ColorFlow.py
    ColorFlowLib\
```

**必须完全重启 Resolve**，然后打开：

```
Workspace > Workflow Integrations > ColorFlow
```

卸载：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall
```

## 四页使用说明

### Tab1 素材分析

- 当前镜头缩略图预览；
- 自动读取当前镜头的分辨率、帧率、编码、位深、白平衡元数据和 Log 类型；
- 高光接近裁切、暗部裁切、高饱和/色域风险、素材与时间线分辨率/帧率不匹配会显示警告；
- **一键处理警告**：把曝光/白平衡/高饱和/灰片修正合成一个 DCTL，写入 04 之后的空白修复节点；02–04 还原节点不动，最后一个空白节点保留给匹配；
- “按素材建线”会取最大分辨率和最常见帧率创建时间线，按名称自然排序；
- 当前没有时间线时，界面仍可打开，不会报错退出。

元数据字段因相机/编码而异；插件会用通用关键字匹配 `White Balance`、`Color Temperature`、`Color Space`、`Gamma` 等字段。

### Tab2 一级调色

- 当前镜头缩略图预览，和写入后的状态对照；
- **套用节点模板**：套用 `~/Documents/ColorFlow/Templates` 下的 DRX 模板；一键还原会自动把节点命名为 `01 降噪 / 02 曝光 / 03 色温 / 04 饱和 / 匹配`，用户原始 DRX 不会被改写；
- **从当前节点链生成模板**：复制当前时间线，重置副本节点调色，导出 DRX 后删除副本。原始时间线不会被修改；
- **一键还原（分节点，默认）**：优先套用当前节点模板（最后保存的模板），01 降噪保持不变，02 曝光、03 色温、04 饱和分别写入，最后一个空白节点留给颜色匹配；没有用户模板时使用发行包内置的五节点模板，节点不足时回退单节点兼容还原；
- **自动黑白场**：根据画面 p01/p99 生成柔和黑白点拉伸 DCTL；
- **自动白平衡**：用近中性中间调估计 R/G、B/G 偏差；
- **自动曝光拉伸**：按中间调 0.18 目标计算曝光增益；
- **LUT 图库**：扫描 Resolve 主 LUT 目录，按 SLog3 / ARRI / HLG / CLog / Rec.709 / 自定义分类；用固定人像标准图生成可见缩略图，支持分页、选中大图预览和套用；也可浏览外部 LUT，插件会复制到 `LUT/ColorFlow/UserLUTs`；
- 默认写入前创建调色版本，支持“撤销上次写入”。

Resolve 公开 API 不能直接新建节点，所以节点树通过 DRX 模板实现。没有用户模板时，一键还原会尝试使用已安装的五节点模板；仍不可用时，自动校正写入当前选中的空白节点。

### Tab3 镜头匹配与肤色

- 参考 / 目标 / 结果三图预览；
- 参考来源支持当前帧、画廊静帧和本地单帧图片；
- 把播放头放在参考镜头上，点击“拾取当前帧”；也可以点“从画廊引用”选择静帧，或点“本地单帧”导入图片；
- 选择“选中镜头 / 整条时间线”，点击“匹配参考色调”；
- Color 页面没有时间线选中片段时，“选中/当前镜头”会自动使用播放头下的镜头；裁剪/分割后的片段同样适用；
- 匹配统计量：中间调曝光、近中性轴白平衡、对比、饱和度；
- 匹配强度可调（默认 60%），色差过强时降低后重试；
- 匹配写入最后一个空白节点，不覆盖 02–04 的还原节点；
- **撤销本次匹配**使用 `~/Documents/ColorFlow/Backups/last_batch.json`，面板重启后仍可回退最近一次批量匹配；
- 肤色限定使用 YCbCr 肤色遮罩 DCTL，可调色相、饱和度、亮度，并可选背景降饱和。

**AI 人脸检测没有内置**。公开脚本接口不提供人脸框或原生 Qualifier 节点；当前用肤色色相/YCbCr 遮罩实现“肤色限定器”的等效效果。若需要真正的人脸检测，需要额外接入 OpenCV/MediaPipe，并把检测框转换成 DCTL 空间遮罩。

### Tab4 预设与批量

- 当前镜头缩略图预览；
- “保存为 DRX 预设”：`GrabStill → GalleryStillAlbum.ExportStills(..., "drx")`，保存到 `~/Documents/ColorFlow/Presets`；
- 预设支持分类、收藏、删除、应用到当前镜头、批量应用到选中镜头/整条时间线；
- “校验整条时间线并输出报告”：逐镜头抓取缩略图，检查裁切、不匹配、Log 与影调统计，生成 HTML 报告到 `~/Documents/ColorFlow/Reports`。

DRX 导出/回套依赖 Resolve 的 Gallery 接口，建议首次使用时先在一个测试镜头上验证；插件会在每个批量操作前创建调色版本。

## 安全模型

1. 写入前默认创建调色版本，原版本保留；
2. 写入失败自动载回原版本；
3. “撤销上次写入”恢复本次操作涉及镜头的版本；
4. 默认只写“疑似空白”节点；写非空节点需要显式勾选；
5. 写 DCTL/CDL 时自动启用目标节点，否则禁用的节点不会产生画面变化；
6. 不删除原始时间线或素材；模板生成使用时间线副本。

## 稳定性

- UI 泵送带重入保护，避免 `StepLoop()` 在按钮事件中递归；
- 长操作互斥，处理中重复点击不会启动第二个批量任务；
- 批量匹配/预设/报告逐镜头检查取消标记，处理中关闭面板会取消后续镜头；
- 当前帧预览使用全分辨率静帧导出，刷新通常需要 0.5–1 秒，不会逐帧自动刷新。

## 已验证

在 DaVinci Resolve Studio 21.0.4 + Windows 上已完成：

- 23 个纯 Python 单元测试通过（含 LUT 1D/3D、混合 Shaper、PNG 预览）；
- v1 核心链路实测：6 个 5120×2700 / 30fps 素材建线、起始时间码 `01:00:00:00`；
- 复制时间线写入 DCTL 到 06 号节点，实际渲染帧 +1EV 探针像素差 31.03，版本回退后 0.00；
- `AddVersion` 备份、`ResetAllGrades` 还原、`LoadVersionByName` 回退后节点工具与 LUT 恢复；
- v3 扁平四工作区面板成功构建，当前镜头缩略图正常显示，控件不再互相重叠；
- LUT 图库实测加载 340 个条目、24 个/页；中文 / English 分类筛选和翻页正常；
- 图库关闭按钮实测可立即隐藏窗口，不再残留测试窗口；
- 测试时间线副本已删除，原时间线未修改。

> 安装或更新后需要完全重启 Resolve，旧面板实例才会被清空。预览捕获前插件会自动切到 Color 页面。

## 已知限制

- 缩略图分析基于 Resolve 返回的镜头缩略图（通常 288×162），适合统计匹配，不做像素级克隆；
- LUT 图库缩略图目前只为 `.cube` 生成；`.dat`、`.dctl`、`.ilut`、`.olut`、`.3dl` 仍可列出并套用，但选中区会提示暂无缩略图；
- 多视频轨道叠加在同一时间点时，请独奏目标轨道或把目标镜头放在最上层；
- 色域越界是缩略图高饱和/裁切近似，不是真正的场景域色域分析；
- 肤色限定是 YCbCr 遮罩，不是原生 Qualifier 节点；
- 当前只处理节点堆栈第 1 层；
- DCTL 写入成功只代表 Resolve 接受路径，实际编译仍需看画面；v1 已用实际帧验证过同链路。

## 开发

```powershell
python -m unittest discover -s tests -v
```

模块结构：

```
ColorFlow.py                    Resolve 注册入口（加载 ui_v2）
ColorFlowLib/analysis.py        图像统计、自动模型、CDL/DCTL、肤色 DCTL
ColorFlowLib/features.py        元数据、LUT 扫描、DRX 预设、模板、报告
ColorFlowLib/lut_gallery.py     .cube 解析、标准图缩略图、预览缓存
ColorFlowLib/resolve_bridge.py  Resolve API、抓帧、节点、版本、LUT 写入
ColorFlowLib/timeline_tools.py  分辨率/帧率/时间码/建线规划
ColorFlowLib/ui_v3.py           四工作区 UIManager 面板（当前入口）
ColorFlowLib/preview.py         纯 Python 缩略图 PNG 输出
assets/                         LUT 图库固定标准预览图
ColorFlowLib/ui_v2.py           上一版面板（保留兼容）
ColorFlowLib/ui.py              v1 单页面板（保留兼容）
tests/                          单元测试与 Resolve 联调脚本
```

