# 当前工作交接

- **状态：** 当前已授权的建模、审查修复、提交与推送均已完成；没有正在实施的代码任务。
- **更新时间：** 2026-09-21T18:01:16+08:00。
- **仓库：** `/Users/miclle/github/miclle/vinyl-record-player`；远端 `git@github.com:miclle/vinyl-record-player.git`。
- **分支 / 基准：** `main` / `main`。
- **实现基线 HEAD / 本文提交前最后推送：** `3c050508ac3a9acfbb8af5953f32ab0e6563f0cf`。
- **上游：** `origin/main`；编写时实现基线 ahead/behind 为 `0/0`，已核对远端 SHA。本文的文档提交是其后续提交，可用 `git log -1 --format=%H -- docs/current-work-handoff.md` 定位。
- **交接编写者 / 接手者：** 当前 Codex 会话 / 未指定。
- **传递状态：** transferable（本次文档提交推送完成后）；通过远端 `origin/main` 传递本文及实现基线，无须另外复制本地文件。接手者需有仓库读取权限；具体接手者权限未验证。

## 目标与授权边界

用户要制作外观参考 HYM LUMI Walnut 的一体式黑胶唱片机，内置一个大低音、两个小高音，扬声器尺寸先占位，机芯已指定为淘宝“28高端弯臂机芯全套餐装好直接用 自动回臂”。当前成果是概念装配与机芯安装核对，并非可加工设计。

用户最后询问为何有三个 CAD 文件。已解释版本和依赖关系，并建议未来统一主模型；**用户尚未要求执行文件清理或生成器重构**。用户随后明确要求提交并推送本文；授权范围仅为交接文档，不包含模型清理或重构。

## 当前成果

### 已完成

- `5f4928d`：可重建的外壳、一个下向低音与两个前向高音布局、CAD/STEP、尺寸图、预览、参数和基线验证。
- `3c05050`：指定弯臂机芯外观占位、保守下探空间、干涉报告、独立装配、参考图片与文档。
- 同一提交修复重建覆盖保护：`tools/mechanism_study.py` 同时检查文档名和解析后的文件路径。重新打开目标文件、通过符号链接打开目标文件，均拒绝重建；测试检查磁盘输出和内存中未保存修改保持不变。
- 审查、5 项回归测试、提交及推送完成；工作区在创建本文前干净。

### 部分完成与阻塞

弯臂机芯仅建立示意外观与安装空间诊断，承载板开口、弹簧支点及固定孔未设计。真实安装适配依赖商家底部轮廓、安装基准、下探位置及深度、孔距、上部高度等数据。扬声器和电子接口仍待选型或实测。

### 未开始 / 范围外

- 统一一个主 CAD、删除旧产物、消除生成脚本对旧 FCStd 的依赖：仅为建议，未实施。
- 加工图、公差、声学与分频、自动回臂运动、循迹、电气功能、样机性能：未验证。
- `docs/superpowers/plans/2026-09-21-lumi-cad.md` 是历史记录；其中双单元、早期检查数及“未推送”等文字不是当前状态。后续设计待办以 `docs/selected-mechanism.md` 的“后续适配与重建”为准；没有独立 TODO 文件。

## 三个模型与依赖

| 文件 | 角色与处理原则 |
|---|---|
| `cad/lumi-dual-driver.FCStd` / `.step` | 最初双单元旧版，仅作历史对照，当前脚本不生成。 |
| `cad/lumi-three-driver.FCStd` / `.step` | v0.2 外壳与三扬声器基线，包含通用机芯占位；由 `tools/build_model.py` 生成。 |
| `cad/lumi-selected-mechanism-fit.FCStd` / `.step` | 当前应查看的弯臂机芯核对版；由 `tools/mechanism_study.py` 读取已保存的 three-driver FCStd，复制外壳等分组后替换机芯。 |

不能直接删除 three-driver FCStd：核对版生成器与 `tests/test_mechanism_study.py` 依赖它。若以后获授权统一模型，应先调整生成链、验证及文档，再移除历史产物；历史由 Git 保留。

## 设计判断与风险

- 外壳基线为 448.6 × 345.5 × 214.2 mm；214.2 mm 暂作闭盖总高，参考图测量基准未明确。
- 一个低音朝下、两个高音朝前；法兰分别 Ø116 / Ø54 mm，开孔 Ø100 / Ø40 mm，箱内深度 65 / 30 mm，均为占位。
- 商品 `712086565319`、SKU `5162746531784`。用户提供的尺寸图是直臂款：355 × 280 mm 和边缘 10 mm 标注不能当作弯臂款已确认规格，10 mm 更不是机芯总高或下探深度。淘宝详情此前未能读取。
- 45 mm 下探深度是本项目假设；矩形包络比真实局部底部轮廓保守。安装面 Z150、声腔顶板上表面 Z136，仅有 14 mm；按该假设需多 31 mm 空间。重叠不证明实物必然碰撞，不应直接整体降低声腔顶板。
- v0.2 的唱盘 Ø300、唱臂轴距 200、有效长度 218 mm 不适用于选定机芯。核对版唱臂为近似停放姿态，不做循迹承诺。
- `installation_released=false` 是当前真实状态。几何通过与装配放行是不同结论。
- `FitAnalysis` 中的包络和干涉实体默认隐藏，STEP 不包含诊断实体。FCStd 为脚本生成的静态 `Part::Feature`，手工编辑应另存，改 JSON 需重建。

## 工作区

- **文档提交前：** 仅 `docs/current-work-handoff.md` 未跟踪；没有其他暂存或已跟踪修改，没有未推送提交。
- **交付内容：** 本文随独立文档提交纳入版本控制并推送至 `origin/main`；接手时使用 `git status --short --branch` 核对实时状态。
- **需保护：** 不覆盖 FreeCAD 内手工修改，不为清理文件而 stash、reset、切换分支或删除未知内容。接手时重新检查实时工作区。

## 验证证据

以下程序测试来自本会话提交前的实际执行；本次 handoff 只核对状态与既有报告，未重跑几何构建。

| 命令 / 检查 | 结果与范围 |
|---|---|
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib /Applications/FreeCAD.app/Contents/Resources/bin/python -m unittest discover -s tests -v` | 5 tests，OK；涵盖重开/符号链接保护、包络深度、宏重载、参数快照、尺寸标注。 |
| 同一 Python 执行 `-m unittest discover -s tests -p test_mechanism_study.py -v`（修复前） | 新增保护测试的普通路径、符号链接两个子用例失败，证实可复现；修复后全部通过。 |
| `cad/validation.json`；生成命令为同一 Python 执行 `tools/validate_model.py` | 已保存的 v0.2 报告 18 项通过；不覆盖核对版。该命令会改写报告。 |
| `cad/mechanism-fit-report.json`；由 `tools/mechanism-study.FCMacro` 生成 | 实体有效性、STEP 有效性、实体数、体积 4 项通过；安装未放行，保守包络存在重叠。 |
| 审查时独立读取交付 FCStd / STEP | 各 66 个实体，体积差约 -2.6e-7 mm³；配置快照与基线 SHA 一致。 |
| 两张 `previews/selected-mechanism-*.png` | 已人工视觉核对实际 CAD 渲染。 |
| `git diff --cached --check`（提交前） | 通过。 |
| 自动回臂、播放、声学、实物安装 | 未验证。 |

## 接手先读

1. `AGENTS.md`、本文及 `README.md`：仓库规范和版本入口。
2. `docs/selected-mechanism.md`、`cad/selected-mechanism.json`、`cad/mechanism-fit-report.json`：当前假设及待办。
3. `tools/mechanism_study.py`、`tools/mechanism-study.FCMacro`、`tests/test_mechanism_study.py`：基线依赖、保护逻辑和回归覆盖。
4. `tools/build_model.py`、`cad/parameters.json`、`tools/validate_model.py`：基线生成与验证。
5. `references/selected-mechanism/README.md` 与两张图片：来源和尺寸限制。图片版权不由仓库 LICENSE 授权。

## 后续行动

当前已授权任务已完成，没有应自动继续实施的变更。恢复上下文的第一步是在仓库执行：

```sh
git status --short --branch
git rev-parse HEAD
git rev-list --left-right --count 'HEAD...@{upstream}'
rg -n 'lumi-(dual-driver|three-driver|selected-mechanism-fit)' tools tests README.md AGENTS.md docs
```

完成条件：确认当前 HEAD 包含上述实现基线及本文的文档提交，识别新增工作区变更，理解当前生成依赖；若存在后续实现变更，先核对新实现再使用本文。后续以用户新指令为准：

- 若要求统一模型：先从 `tools/mechanism_study.py:build_study` 与 `tools/build_model.py` 设计统一生成链，再更新产物路径、测试和文档；验收须能从源码重建，且不再读取被移除的历史 CAD。
- 若提供实测机芯尺寸：先更新 `cad/selected-mechanism.json` 及尺寸依据，再改安装结构；重新生成报告、STEP 和预览，不沿用旧的 31 mm 结论。
- 修改后运行上述完整测试并做相关 CAD 验证与视觉核对。是否提交、推送按新请求执行。

## 环境与传递

macOS，FreeCAD 1.1.1。捆绑 Python 为 `/Applications/FreeCAD.app/Contents/Resources/bin/python`，库目录为 `/Applications/FreeCAD.app/Contents/Resources/lib`；先导入 `FreeCAD` 再导入 `Part` 或 `TechDraw`。其他机器需替换安装路径。完整预览需 FreeCAD GUI 执行宏，纯 Python 只构建几何和报告。没有需要传递的秘密配置。

首次交接，无前置交接文档。实现范围已完成；传递渠道为 `origin/main` 的独立文档提交。推送并核对远端 SHA 后即满足资料可传递条件；接手者仍需拉取该提交并执行上述状态核对。
