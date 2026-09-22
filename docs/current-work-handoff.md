# 当前工作交接

- **状态：** 旧模型清理与相关文档同步已完成，由本次清理提交承载；发布状态以实际远端核对为准。SC-2103 音腔布局及审查修复此前已交付；整机加工与声学验收未完成。
- **提交前状态核对时间：** 2026-09-22T09:03:15+08:00。
- **仓库：** `miclle/vinyl-record-player`；本机目录 `/Users/miclle/github/miclle/vinyl-record-player`。
- **分支 / 基准分支：** `main` / `main`。
- **实现提交：** `2bb41bf8410999b18e20d82dbe4c81baad0a3d8f`，`feat(cad): redesign SC-2103 acoustic chambers`。
- **提交前 HEAD / 上游快照：** `978d327f20b87ed6d0372529beff660f3c2ef81f`，`docs: refresh acoustic design handoff`；本地 `origin/main` 与 HEAD 一致，ahead/behind 为 `0/0`。该次核对未查询实时远端；清理内容由此快照之后的本次提交承载。
- **当前整理者 / 接手者：** 本任务 / 未指定。
- **传递范围：** 此前实现与文档已发布到 [GitHub 仓库](https://github.com/miclle/vinyl-record-player)；本次旧模型删除与文档同步需取得承载本文的清理提交，仅获取上述旧 HEAD 不包含本次清理。
- **本交接文档版本：** 提交后用 `git log -1 --format=%H -- docs/current-work-handoff.md` 定位，并结合 `git status` / `git diff` 识别后续本机修改。

## 目标与当前成果

在 448.6 × 345.5 × 214.2 mm 的 LUMI 参考外廓内，重新安排用户的 Shockwave SC-2103 拆机扬声器、电源和功放。用户确认原箱和倒相管均已遗失；本轮交付可核对的空间方案、试验倒相结构和验证器，未把几何检查当作声学性能或加工放行。

| 范围 | 当前状态 |
|---|---|
| 三个音腔及电子布局 | 已完成：左右 Ø78 × 40 mm 全频朝前，各约 1.14 L 密闭试验腔；Ø132 × 65 mm 低音移到后排 Y=247 mm 并朝下，约 4.08 L 保守净容积；电源左后、功放右后 |
| 低音倒相管 | 已建模：后置、内径 32、初始物理长度 160 mm；120／160／200 mm 空间已检查。密封、紧固、公差和声学调谐未完成 |
| 审查发现的验证器问题 | 已修复：探测点随音腔边界变化；净容积扣除所有已建模入腔部件及保守安装包络，重叠占用只扣一次 |
| CAD 与关联交付物 | 已完成并随实现提交发布：基线与弯臂核对版 FCStd／STEP、零件表、报告、尺寸图及预览 |
| 左右全频倒相接口 | 未实施：可封堵、可换管接口仅为讨论建议，当前模型左右仍为密闭腔；方案入口见[音腔专题](audio-layout.md#左右全频腔的后续方案) |
| 选定弯臂机芯适配 | 部分完成：已有占位和干涉诊断，真实底部尺寸、安装孔与运动范围缺失，`installation_released=false` |
| 声学、电气、热与隔振验证 | 未开展实物验收；开孔、紧固和制造接口仍需实测 |
| 历史模型清理 / 统一主模型 | 后续已清理旧双单元 FCStd / STEP；保留两份当前模型，核对版仍依赖基线，尚未统一主模型 |

## 工作区与传递方式

本次工作区删除 `cad/lumi-dual-driver.FCStd` / `.step`，并更新 `AGENTS.md`、`README.md`、`docs/selected-mechanism.md`、历史实施记录及本文。这些修改由本次清理提交承载；接手时用 `git status --short --branch` 和 `git diff` 核对。

旧双单元文件可从 Git 历史找回。两份现有 FCStd、配套 STEP、参数、生成代码与验证报告均未改变；机芯核对版仍读取已保存的三单元基线。用户已授权将清理与文档更新提交并推送；发布结果由推送后的远端核对确认。

不要覆盖接手机器 FreeCAD 中未保存的手动修改。本任务前一轮使用独立 FreeCAD 进程生成交付物，没有关闭用户原 GUI 会话；磁盘文件与 GUI 中仍打开的旧文档可能不同。手动修改应先另存，再按重建要求关闭相关输出文档。

## 决策与边界

- `cad/parameters.json` 版本为 `v0.4-sc2103-layout`。外径和总高采用用户尺寸，开孔 Ø100 / Ø40 mm、3 mm 法兰厚度与背部轮廓仍是假设。
- `fullrange` 是参数键与角色名称，`TweeterLeft` / `TweeterRight` 仅保留为稳定对象 ID；不能据旧 ID 把单元当作纯高音。
- 原箱及 T/S 参数缺失。左右密闭、低音 32 × 160 mm 管均是试验初值，没有验证其优于其他方案。左右倒相接口的建议不等于已实现功能。
- 净容积由保存的音腔几何扣除已建模占用得到；扬声器与变压器使用保守实心包络，管道扣除整个外廓。尚未建模的吸音材料、支柱、密封件与线缆未计入。
- 基线含通用机芯；核对版替换为选定弯臂机芯外观。基线的 `BearingPocket` 是通用轴承的密封避让杯，不能作为弯臂机芯已适配的证据。

## 验证证据

下表 FreeCAD 测试与几何验收沿用此前实现提交的记录；本次只核对文件、依赖、文档链接、保存报告和基线哈希，没有重建 CAD 或重跑测试。

| 命令或检查 | 结果与边界 |
|---|---|
| `PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib /Applications/FreeCAD.app/Contents/Resources/bin/python -m unittest discover -s tests -v` | 前一轮 12 项测试通过；含后隔板移至 Y=100 mm、功放及变压器入腔排量、串腔、堵管、三种管长及既有回归 |
| `PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib /Applications/FreeCAD.app/Contents/Resources/bin/python tools/validate_model.py` | 前一轮 30 项基线检查通过；本次读取 `cad/validation.json` 核对，63 个零件、74 个实体 |
| `tools/mechanism-study.FCMacro` 生成的 `cad/mechanism-fit-report.json` | 4 项几何／STEP 检查通过；本次重新核对 `base_sha256` 与输入基线 FCStd 一致；安装仍未放行 |
| 保存文件及预览核对 | 前一轮已回读 FCStd／STEP 并目视检查内部、俯视、后口和机芯核对图；两套 FCStd 均保留 GUI 状态 |
| 本次清理与文档检查 | `git diff --check`、相关本地路径／链接／锚点、两份保留 FCStd 与 HEAD 字节一致、旧文件无脚本／测试依赖及报告数据核对 |
| 实物及声学试验 | 未执行；不能用上述检查推导频响、允许功率、气密、散热、声反馈或播放性能 |

## 阻塞与有效后续工作

本轮实现交付没有未解决的代码阻塞。整机适配仍缺弯臂机芯真实安装资料：355 × 280 mm 来自直臂配图，45 mm 下探为项目假设。该包络与顶板、倒相管等重叠；台面 Z=150 与音腔顶板顶面 Z=136 相距 14 mm，假设包络多需 31 mm，不代表实物必然干涉。

后续工作沿用正式专题，不另维护第二套 TODO：

- [左右全频倒相方案与试装](audio-layout.md#左右全频腔的后续方案)：新增接口前核对出管空间、所属音腔、可封堵结构，并扩展验证器的临时封口与气路检查。
- [机芯后续适配与重建](selected-mechanism.md#后续适配与重建)：取得底部实测轮廓，再设计开口、支点和局部避让。
- [加工前资料清单](design-basis.md#进入加工前必须补齐)：扬声器安装接口、材料、电子接线、固定与实物验收。

`docs/superpowers/plans/2026-09-21-lumi-cad.md` 属于历史计划，不是当前任务或验收依据；本次仅更新开头的历史状态与旧文件去向说明，保留当时的完成记录。

## 接手的第一步

本次清理已完成，没有需要自动恢复的代码任务。接手者先在仓库根目录核对版本和工作区，不自动重建或覆盖 CAD：

```sh
git status --short --branch
git diff --stat
git diff -- docs/current-work-handoff.md
git fetch origin
git log -1 --format=%H -- docs/current-work-handoff.md
git merge-base --is-ancestor 2bb41bf8410999b18e20d82dbe4c81baad0a3d8f HEAD
git rev-list --left-right --count HEAD...origin/main
```

完成条件：确认本地包含实现提交和最新交接文档，识别并保护本机修改，明确与 `origin/main` 的差异。随后按用户的新任务选择上述专题中的有效工作；不要继续执行已关闭的审查修复，也不要把讨论中的全频倒相接口当作已经存在。

## 文件入口与环境

| 文件 | 用途 |
|---|---|
| [AGENTS.md](../AGENTS.md)、[README](../README.md) | 项目约定、基线生成与验证入口 |
| [音腔设计](audio-layout.md)、[参数](../cad/parameters.json) | 当前三音腔、倒相管、电子布局与估算口径 |
| [机芯专题](selected-mechanism.md)、[机芯参数](../cad/selected-mechanism.json) | 选定款式、假设与未放行事项 |
| [验证器](../tools/validate_model.py)、[回归测试](../tests/test_regressions.py) | 探测点、扣容积、安装空间和导出检查 |
| [基线报告](../cad/validation.json)、[核对报告](../cad/mechanism-fit-report.json) | 两套不同范围的验证结果 |

使用 macOS FreeCAD 1.1.1；其他机器需调整 `/Applications/FreeCAD.app/Contents/Resources/bin/python` 和库目录。完整生成顺序是基线 `tools/build.FCMacro` → 独立验证 → `tools/mechanism-study.FCMacro`；核对版读取已保存的基线，不自动应用 JSON 或 GUI 未保存修改。GUI 保存用于保留颜色和可见性，纯 Python 入口不输出完整预览。无需取得本机临时日志才能接手；上述测试可在对应提交重新执行。

本文件继续沿用 `docs/current-work-handoff.md`。跨机器接手时应确认已取得承载本文的清理提交，并保护接手机器上的未提交修改；不能把此前实现已发布等同于本次清理已发布。
