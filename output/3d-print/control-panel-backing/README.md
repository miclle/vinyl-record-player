# 旋钮面板底板

独立底板夹在现有 65 × 160 × 3.5 mm 旋钮面板和 10 mm 木板之间。仅新增底板，原面板、电路板孔位、定位条及整机模型均未修改。

- 板厚 2 mm，高度 160 mm。最左侧增加朝正面的连续凸条：宽 3 mm、长度 130 mm；总高度 8 mm 包含板厚，即高出板面 6 mm。凸条 X=-8…-5、Y=30…160，与底板一体成形。
- 以原旋钮面板正面左上角为原点，X 向右、Y 向下。Y=0…30 的上部宽 65 mm；Y=30…160 向左延伸 8 mm，下部宽 73 mm。新增左边为 X=-8，原右边仍为 X=65。
- 主窗口：X=2.8…62.2，Y=12…148，即 59.4 × 136 mm。两条定位条的外侧和端部名义间隙均为 0.3 mm。
- PCB 下方追加避让口：X=14.5…50.5，Y=148…158，即 36 × 10 mm。它与主窗口连通；已知 PCB 下缘 Y=157，纵向名义留 1 mm。实际 PCB 宽度、元件及深度位置未确认，此口不构成完整电路板安装验证。木板现有窗口下边仍为 Y=148，原先的木板/PCB 试装条件仍需核对。
- 固定孔为四个 Ø3.5 mm 通孔，坐标为 (9.5,6)、(55.5,6)、(9.5,154)、(55.5,154)。底板保留各 Ø7 mm 螺丝头投影范围内的材料；孔位沿用原面板，不因左侧加宽而平移。
- 七个功能孔及其轴线均落在主窗口内，不在底板上重复加工小圆孔，避免底板阻挡连接器、旋钮或 LED 背部。

安装叠放：旋钮面板 → 2 mm 底板 → 10 mm 木板。定位条仍高 10 mm，穿过底板后伸入木板 8 mm。使用相同螺丝时，进入木板的长度减少 2 mm；长度、螺纹咬合和实物夹紧需核对。左侧延伸区不额外加固定孔，与原面板共用四孔。

## 文件与打印

- `Control-panel-backing.FCStd`：独立 FreeCAD 模型，包含参数快照和可见视图。
- `Control-panel-backing.step`：单实体工程交换模型。
- `Control-panel-backing.stl`：打印文件，平面已经放在 Z=0，包络 73 × 160 × 8 mm。单位毫米，导入比例 100%；底板背面贴热床、凸条朝上，无悬空结构。STL 无颜色信息，可在 Bambu Studio 对整个对象指定黑色。
- `Control-panel-backing.json`：孔位、外轮廓、窗口、原文件哈希及导出验证结果。
- [保存模型预览](../../../previews/control-panel-backing-model.png)：等轴测视图。
- [尺寸及叠放示意](../../../previews/control-panel-backing.png) / [SVG](../../../previews/control-panel-backing.svg)：示意标识不属于底板上的实体文字，也不是 1:1 纸模板。

FreeCAD 模型沿用原面板 CAD 坐标 X=x、Y=160−y，底板 Z=0…2、左凸条 Z=2…8；安装时整体平移 -2 mm，底板为 Z=-2…0、左凸条为 Z=0…6。STL 打印坐标为 X=x+8、Y=160−y、Z=0…8，不应直接以 STL 原点与旧模型叠放。STEP/FCStd 保持原面板坐标便于装配。

## 重新生成与验证

关闭底板目标文档，手动修改另存；在 FreeCAD GUI 执行 `tools/build-control-panel-backing.FCMacro`。参数来自 `cad/control-panel-backing.json` 和 `cad/control-panel.json`，不重建整机。

```sh
PYTHONPATH="${FREECAD_RESOURCES:?请先设置 FreeCAD 运行环境}/lib" \
  "$FREECAD_RESOURCES/bin/python" -m unittest discover -s tests -p 'test_control_panel_backing.py' -v
rsvg-convert previews/control-panel-backing.svg -o previews/control-panel-backing.png
```

验证覆盖保存的阶梯外形/厚度、左凸条总高/净高/宽度/长度、与原面板无交叠、主窗口及底部避让、四孔和完整螺丝头承压范围、定位条无交叠、FCStd/STEP 一致，以及 STL 单组件、封闭、无非流形边和自交。以上为静态几何及网格验证；2 mm 底板强度、打印实物配合与 PCB 安装仍需试装。
