"""Export a vector A4, 1:1 paper cutting template from the inlet parameters.

The template is viewed from outside the rear panel: increasing model X runs
left on the paper. Its right and bottom edges register on the formed Back.
Requires ReportLab in a regular Python runtime; never modifies the CAD.
"""
import argparse
import json
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
MM = 72 / 25.4


def export_template(parameters, output, font):
    p = parameters
    s = p['ac_inlet']
    panel_bottom = p['foot_height'] + p['wall']
    panel_height = p['cabinet_top'] - panel_bottom
    right_offset = s['center_x'] - p['wall']
    bottom_offset = s['center_z'] - panel_bottom
    width, height, radius = (s[k] for k in
                             ('cutout_width', 'cutout_height', 'cutout_radius'))
    pitch, diameter = s['mount_hole_pitch'], s['mount_hole_diameter']
    # This is a local paper patch, not the full 426 mm panel.
    left, bottom, right = 35, 126, 175
    top = bottom + panel_height
    cx, cy = right - right_offset, bottom + bottom_offset
    if not (0 < radius < min(width, height) / 2 and diameter > 0):
        raise ValueError('Invalid inlet cut dimensions')
    if not (left + 20 < cx - width / 2 < cx + width / 2 < right - 8
            and bottom + 12 < cy - max(height, pitch + diameter) / 2
            and cy + max(height, pitch + diameter) / 2 < top - 12
            and top < 245):
        raise ValueError('Inlet layout does not fit this A4 registration patch')

    pdfmetrics.registerFont(TTFont('TemplateCN', str(font)))
    output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output), pagesize=(210 * MM, 297 * MM))
    c.setTitle('8-F5 AC 插座开孔纸样 / A4 / 1:1')
    c.setAuthor('vinyl-record-player')
    c.setViewerPreference('PrintScaling', 'None')
    c.scale(MM, MM)

    def text(x, y, value, size=9, align='left'):
        c.setFont('TemplateCN', size / MM)
        fn = {'left': c.drawString, 'center': c.drawCentredString,
              'right': c.drawRightString}[align]
        fn(x, y, value)

    def line(x1, y1, x2, y2, width=0.15):
        c.setLineWidth(width)
        c.line(x1, y1, x2, y2)

    def hdim(x1, x2, y, label):
        line(x1, y, x2, y)
        for x in (x1, x2):
            line(x - 0.8, y - 1, x + 0.8, y + 1)
        text((x1 + x2) / 2, y + 2, label, 8, 'center')

    def vdim(x, y1, y2, label):
        line(x, y1, x, y2)
        for y in (y1, y2):
            line(x - 1, y - 0.8, x + 1, y + 0.8)
        c.saveState()
        c.translate(x - 2, (y1 + y2) / 2)
        c.rotate(90)
        text(0, 0, label, 8, 'center')
        c.restoreState()

    def cross(x, y, size=2):
        line(x - size, y, x + size, y)
        line(x, y - size, x, y + size)

    text(20, 277, '8-F5 AC 插座开孔纸样', 18)
    text(20, 267, 'A4 竖向 · 1:1 · 单位 mm · 横向安装', 10)
    text(20, 258, '打印选择“实际大小 / 100%”，关闭“适合页面”及自动缩放。', 9)
    line(20, 252, 190, 252, 0.3)

    # Dashed outline is paper trimming, never a wood cutting contour.
    c.setLineWidth(0.18)
    c.setDash(2, 1.5)
    c.rect(left, bottom, right - left, panel_height, stroke=1, fill=0)
    c.setDash()
    text((left + right) / 2, top + 3, '虚线框：裁纸边界（后板外侧局部）', 9, 'center')
    text(left + 4, top - 7, '此面朝外；从箱体后方看，插座位于右侧。', 8)
    text(right, bottom - 6, '底边：对齐后板下边', 9, 'right')
    c.saveState()
    c.translate(right + 5, (bottom + top) / 2)
    c.rotate(90)
    text(0, 0, '右边：对齐后板右边', 9, 'center')
    c.restoreState()

    c.setLineWidth(0.25)
    c.roundRect(cx - width / 2, cy - height / 2,
                width, height, radius, stroke=1, fill=0)
    for sign in (-1, 1):
        hole_y = cy + sign * pitch / 2
        c.circle(cx, hole_y, diameter / 2, stroke=1, fill=0)
        cross(cx, hole_y, 3)
    cross(cx, cy, 3)
    text(cx, cy + 4, '开孔区域', 9, 'center')
    text(cx, cy - 7, f'{width:g} × {height:g}  R{radius:g}', 9, 'center')

    hdim(cx - width / 2, cx + width / 2, cy + pitch / 2 + 10, f'{width:g}')
    for x in (cx - width / 2, cx + width / 2):
        line(x, cy + height / 2 + 1, x, cy + pitch / 2 + 11)
    vdim(cx - width / 2 - 7, cy - height / 2, cy + height / 2, f'{height:g}')
    vdim(cx + width / 2 + 13, cy - pitch / 2, cy + pitch / 2, f'孔距 {pitch:g}')
    for y in (cy - pitch / 2, cy + pitch / 2):
        line(cx + 4, y, cx + width / 2 + 14, y)
    text(cx - 7, cy - pitch / 2 - 4, f'2 × Ø{diameter:g} 贯穿孔', 8, 'right')
    hdim(cx, right, bottom + 13, f'中心距右边 {right_offset:g}')
    line(cx, bottom + 12, cx, cy - pitch / 2 - 5)
    vdim(left + 20, bottom, cy, f'中心距下边 {bottom_offset:g}')
    line(left + 19, cy, cx - width / 2 - 12, cy)

    text(20, 110, '使用方法', 11)
    text(20, 102, '1. 用尺核对下方 100 mm 标尺及 50 × 50 mm 方框，横竖均应一致。')
    text(20, 95, '2. 沿虚线框裁下纸样，将印字面朝外贴在后板外侧。')
    text(20, 88, '3. 纸样右边、底边分别贴齐后板右边、下边；标记两孔中心及圆角轮廓。')
    text(20, 81, '4. 实线孔轮廓为成品边界；锯缝留在孔内侧，修至尺寸后用实物试装。')
    text(20, 70, f'后板成形尺寸：{p["width"] - 2 * p["wall"]:g} × {panel_height:g} × {p["wall"]:g} mm', 8)
    text(20, 64, '孔尺寸按现有 CAD 与商家图；实际配合、板厚适配及紧固须用实物确认。', 8)

    hdim(20, 120, 38, '100 mm 打印校验线')
    for x in range(20, 121, 10):
        line(x, 36, x, 40, 0.2)
    c.setLineWidth(0.2)
    c.rect(140, 20, 50, 50, stroke=1, fill=0)
    text(165, 47, '50 × 50 mm', 9, 'center')
    text(165, 40, '横竖校验方框', 8, 'center')
    text(20, 24, '只加工孔轮廓及固定孔。', 8)
    text(20, 18, '虚线裁纸框、尺寸线、校验线均为辅助线。', 8)
    text(20, 10, '数据来源：cad/parameters.json · 后视映射：纸面向右为整机 X 减小。', 7)
    c.showPage()
    c.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', type=Path, required=True,
                        help='Embeddable Chinese TrueType font')
    args = parser.parse_args()
    p = json.loads((ROOT / 'cad/parameters.json').read_text())
    export_template(p, ROOT / 'output/pdf/ac-inlet-cutting-template-A4.pdf', args.font)


if __name__ == '__main__':
    main()
