# 机体分组平面图册

阅读尺寸图前，可先查看[整机全景与组件导览](assembly-guide.md)：另附一份两页 A2 PDF 和两张高清 PNG，以 36 个编号关联当前装配的部件、材料状态和下列图册中的详图号。

基于当前已保存的 `v0.6-ac-inlet` 基线和 `v0.3-fit-study` 选定弯臂核对模型，输出 **3 份 A3 横向矢量 PDF，共 34 页**。轮廓直接由 FreeCAD TechDraw 投影，尺寸由实体的 `optimalBoundingBox(False)` 读取；出图脚本仅读取已重建的 CAD，不修改源文件。

| 图册 | 页数 | 内容 |
|---|---:|---|
| [01 整机与外壳](../output/pdf/01-assembly-and-enclosure.pdf) | 12 | 读图约定、木板备料汇总、闭盖六面图、侧板、底板、后板、格栅与饰条、灯带、防尘盖、铰链、脚垫及同形件位置表 |
| [02 音腔与内部结构](../output/pdf/02-acoustic-and-structure.pdf) | 8 | 内部布置、斜面障板、音腔顶板、左右后板、隔板、轴承避让杯、倒相管、浮动台面、承托梁及弹性支承 |
| [03 机芯与电子部件](../output/pdf/03-mechanism-and-electronics.pdf) | 14 | AC 插座、扬声器、功放、电子预留、变压器、接口板、旋钮、选定弯臂机芯各零件；附基线通用机芯三视总图与尺寸记录 |

## 尺寸与覆盖范围

- 长 X：左右方向；宽 Y：前后方向；高 Z：上下方向。表中数值是装配姿态下的外包络，不按最大边自动排序。原点为机体左前方桌面基准，坐标表记录实体包络最小角。
- 各主要零件给出俯、正、右三个独立命名视图；不同视图可使用不同的标注比例。不是统一第一角或第三角投影排列。打印使用 **A3、100% 实际大小**，尺寸以标注数值为准。
- 厚度与长宽高分别列出。平板给板厚，防尘盖给壁厚；采购总成的未知壁厚或 PCB 厚度，以及实心件不适用的壁厚，明确写在说明中。
- 斜障板现在为真实法向厚 8 mm，矩形备料 426 × 98 × 8 mm，修上下 18° 斜口至安装竖高 90 mm。格栅为 426 × 7 × 3 mm 矩形条，整体后倾 18°、竖向节距 11 mm。
- 木板零件页另列整数备料 L × W × T；第一册汇总 22 块 / 条，同步输出[木板备料 CSV](../cad/wood-cut-list.csv)。备料尺寸不含锯缝、表面处理及装配余量；精确斜切边界和接口孔仍允许小数。
- 同形件采用代表件视图、数量与各安装位置；`AcousticRear` 和 `RearSupport` 各包含两个独立实体，按两块分别出图。
- 覆盖选定机芯版 **58 个物理零件对象**；基线 **64 个对象**也全部有对应视图或附录尺寸记录。基线通用机芯在附录中按总成三视图及逐对象尺寸表表示；不与当前弯臂机芯同时安装。
- 诊断矩形包络及红色干涉体不是实物零件，不作为零件下料图；假设下探深度及剩余净空在机芯总图中记录。

后板已标注横装 AC 开孔 48 × 28 mm、R3 和上下两孔 Ø4.5 / 孔距 40；整机图包含向后突出的 1.88 mm 法兰。插座外形与端子为保守包络，适用板厚、紧固与电气安全待实物确认。

当前默认参数与图中文字一致；修改 AC 开孔参数后，后板零件页的孔标注会读取新参数，但第一册备料汇总中的 `StockNote` 仍可能保留默认尺寸。该问题尚未修复，详见[已知问题与待修项](current-work-handoff.md#已知问题与待修项)。电源线目前仅有[购买记录](../references/ac-inlet/README.md#购买链接)，未作为 CAD 零件或图册对象出图。

图册包含当前已有的开孔直径、定位坐标、后板沉台、倒相管壁厚及法兰信息。小数显示到 0.001 mm 是数值记录精度，**不是公差承诺**。防尘盖为成形外廓，未设计热弯展开、拼接工艺；未建模的螺孔、连接、公差和机芯安装接口仍未定义，不能直接作为生产加工图。

## 重新生成

先按项目原有流程确认两份 CAD 与 JSON 一致；本工具不自动重建 CAD，也不采纳 GUI 中尚未保存的手动修改。它读取源文件的临时副本，校验基线参数快照、机芯参数快照及基线 SHA-256，再检查共用部件的包络和体积一致性。源 SHA-256 写入第一册首页。

从任意目录运行均可，默认路径相对脚本所在仓库解析：

```sh
# 在仓库根目录：提取 CAD 实体、精确尺寸与矢量投影。
PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
  /Applications/FreeCAD.app/Contents/Resources/bin/python tools/drawing_data.py

# 普通 Python 环境需要 reportlab、svglib；使用可嵌入的中文 TrueType 字体。
python3 tools/drawing_pack.py --font /path/to/chinese-font.ttf
```

中间数据保存在忽略的 `tmp/pdfs/drawing-data.json`；最终目录为 `output/pdf/`。`--data`、`--output` 可覆盖默认路径。本机字体默认使用阿里巴巴普惠体常规字重；异机请明确指定字体。图中文字嵌入 PDF，阅读者不需要安装同一字体。

验证：

```sh
PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
  /Applications/FreeCAD.app/Contents/Resources/bin/python -m unittest discover -s tests -v

# 在具有 PDF 依赖的普通 Python 中执行比例回归。
python3 -m unittest discover -s tests -p test_drawing_pdf.py -v

# 每次生成后渲染检查，避免轮廓、尺寸线和文字错位。
pdftoppm -scale-to 1500 -png output/pdf/01-assembly-and-enclosure.pdf tmp/pdfs/01
```

FreeCAD 环境没有 PDF 库时会明确跳过 PDF 比例用例，须用第二条命令补跑。出图检查覆盖实体对象遗漏、复合对象拆分、斜板厚度、投影方向、源文件不变，以及 SVG 像素单位转换造成的 PDF 缩放偏差。
