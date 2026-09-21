# 黑胶唱片机 · LUMI 参考外形

基于 [HYM LUMI Walnut 官方资料](https://www.hym-originals-en.com/products/lumi-turntable-walnut)制作的一低音两高音的一体式唱片机概念 CAD。外形与扬声器布局基线为 **v0.2**；新增 **v0.3 选定弯臂机芯装配核对版**，尺寸仍待确认。

![开盖 CAD 预览](previews/open.png)

## 指定机芯装配核对

已按“28高端弯臂机芯全套餐装好直接用 自动回臂”建立 [FreeCAD](cad/lumi-selected-mechanism-fit.FCStd) / [STEP](cad/lumi-selected-mechanism-fit.step) 示意装配，见 [选型说明与重建方法](docs/selected-mechanism.md)。尺寸图是直臂配图，355 × 280 mm 尚不能视为弯臂款已确认尺寸；暂定 45 mm 下探包络与现有结构重叠，安装方案未放行。

[弯臂预览](previews/selected-mechanism-open.png) · [空间核对图](previews/selected-mechanism-clearance.png) · [核对报告](cad/mechanism-fit-report.json)

## v0.2 基线交付内容

| 文件 | 用途 |
|---|---|
| [FreeCAD 装配](cad/lumi-three-driver.FCStd) | 60 个独立零件，按结构分组，可隐藏、移动和进一步建模 |
| [STEP 装配](cad/lumi-three-driver.step) | 毫米制实体交换，共 69 个实体；三个扬声器各含 4 个子实体 |
| [三视尺寸图 SVG](previews/dimensions.svg) / [PNG](previews/dimensions.png) | CAD 实体投影，含外廓和唱盘尺寸；不是加工图 |
| [闭盖](previews/closed.png) / [开盖](previews/open.png) / [内部布局](previews/internal.png) | 实际 FreeCAD 视口渲染 |
| [底部低音安装](previews/bottom.png) | 低音朝下，底板预留圆孔 |
| [俯视](previews/top.png) / [正视](previews/front.png) / [右视](previews/right.png) | 外形与布局核对 |
| [主要参数](cad/parameters.json) | 修改后通过脚本重建 |
| [零件清单](cad/parts.csv) | 材料说明、包络尺寸和估算标记 |
| [设计依据](docs/design-basis.md) | 官方资料、估算边界与后续选型要求 |
| [验证报告](cad/validation.json) | 实体、关键尺寸、干涉及 STEP 回读结果 |

外观包含胡桃木色侧板、后倾横格栅、银色前沿、黑色台面、左前旋钮、唱盘与唱臂包络、烟灰透明翻盖和脚垫。内部按**一个大低音、两个小高音**预留空间：低音位于中央、朝下安装；两个高音位于前面左右两侧。两个隔板分出中央低音腔和两侧高音空间。保留唱盘与唱臂共用底板、三点弹性支承及电子板空间。

## v0.2 基线参数与精度

外廓为 **448.6 × 345.5 × 214.2 mm**，唱盘直径 **300 mm**，唱臂轴距 **200 mm**，有效长度 **218 mm**。

**214.2 mm 暂解释为闭盖总高**，官网图示未明确测量基准。木壳高度分配、板厚、格栅间距、防尘盖与内部件尺寸均为估算；扬声器均未选定真实型号，先按下表预留。法兰不代表振膜直径，也不是确定的名义英寸规格。

| 占位 | 数量 | 法兰外径 | 开孔直径 | 向箱内预留深度 |
|---|---:|---:|---:|---:|
| 低音，底部朝下 | 1 | 116 mm | 100 mm | 65 mm |
| 高音，前部左右 | 2 | 54 mm | 40 mm | 30 mm |

法兰另向箱外伸出 3 mm。低音的最低点离桌面 23 mm，暂留作出声空间，声学效果及防护网厚度后续验证。安装孔只开概念圆孔，未确定螺孔位置。`parameters.json` 中的 `woofer`、`tweeter` 和 `acoustic_divider_x` 可分别调整单元尺寸、位置和隔板位置。

FCStd 保留独立的 `Part::Feature` 实体；主参数由 JSON 驱动脚本重建，**没有完整的草图约束和自动联动特征历史**。可以在 FreeCAD 中继续直接编辑零件，或修改 JSON 后重新生成。部分细部偏移量在建模脚本中。重建不会保留手动修改，应先另存自己的版本。

## v0.2 基线重建

使用 FreeCAD **1.1.1** 验证。输出写回当前仓库的 `cad/` 和 `previews/`。

1. 按需修改 `cad/parameters.json`。
2. 若已打开 `LumiThreeDriver` 文档，先保存自己的改动并关闭；脚本会拒绝覆盖仍打开的同名文档。
3. 在 FreeCAD 的「宏 → 宏」中选择并执行 `tools/build.FCMacro`。它依次生成 FCStd、STEP、清单、预览和尺寸图。
4. 重新执行下方验证命令，使报告与修改后的模型保持一致。

宏每次直接读取三个本地模块的源代码，支持同一 FreeCAD 会话中修改脚本后重跑。生成参数快照保存在 `GeometryDatums.BuildParametersJSON` 中；改动参数却未重建、或模型缺少快照时，验证会失败。报告分别记录模型版本 `revision` 与请求版本 `requested_revision`。

本机也可以用终端启动宏：

```sh
open -a FreeCAD --args "$PWD/tools/build.FCMacro"
```

命令适用于 FreeCAD 尚未运行时；已经运行时直接在宏窗口执行。脚本使用宏本身所在位置寻找仓库，不依赖终端工作目录。

无图形界面时可只生成几何与 STEP：

```sh
PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
  /Applications/FreeCAD.app/Contents/Resources/bin/python tools/build_model.py
```

该方式不输出渲染、颜色和图形视图；要获得完整交付，请执行 GUI 宏。

## 验证范围

回归测试覆盖重复运行宏、旧模型与新参数不一致，以及非默认尺寸标注；测试在临时目录运行，不覆盖交付文件：

```sh
PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
  /Applications/FreeCAD.app/Contents/Resources/bin/python -m unittest discover -s tests -v
```

v0.2 基线的几何验证（不覆盖选定机芯核对版）：

```sh
PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
  /Applications/FreeCAD.app/Contents/Resources/bin/python tools/validate_model.py
```

v0.2 报告通过全部 **18 项检查**，包括：实体有效性、一低音两高音数量与参数、生成参数快照一致性、外廓、唱盘直径、唱臂轴距及有效长度、闭盖净空、开盖抽样、关键内部包络、实心安装空间、低音离桌面间隙、STEP 回读实体数、体积与边界一致性。闭盖到机芯包络的最小距离为 **11 mm**。

开盖以 5° 步长检查 0–70° 的位置，不是连续运动学验证。内部检查覆盖喇叭实心圆柱安装包络与机芯、电路板、隔板及外壳，另检查轴承、马达和电子板的指定边界，不代表所有装配细节已放行。音腔的实际声学容积、扬声器参数匹配、声反馈、隔振性能、驱动与电气功能尚未验证。

低音加高音的组合仍需后续确定中频覆盖和分频方案。进入加工前需选定扬声器，并补齐已选弯臂机芯的真实安装图、材料、连接方式和公差。**本版不能直接作为原厂精确复刻或生产加工图。**

旧版 `cad/lumi-dual-driver.FCStd` / `.step` 保留供对照，不再由当前脚本生成；基线请使用上方 v0.2 文件，选定机芯请查看独立核对版。
