"""Generate the current control panel's A4, 1:1 wood cutting template.

Reads cad/control-panel.json without changing CAD or the print package.
Run in a ReportLab Python environment with --font pointing to an embeddable
Chinese TrueType font. Solid window boundary is trial geometry; mounting
crosses locate wood pilot centers, whose diameters remain unspecified.
"""
import argparse
import json
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
MM = 72 / 25.4


def export_template(p, output, font):
    w, h = p['width_mm'], p['height_mm']
    window = p['mounting']['wood_window']
    x, y, ww, wh = [window[k] for k in ('x_mm', 'y_mm', 'width_mm', 'height_mm')]
    mounts = [hole for hole in p['holes'] if hole['role'] == 'mounting']
    if not (0 < x < x + ww < w and 0 < y < y + wh < h and len(mounts) == 4):
        raise ValueError('Invalid wood window or mounting layout')
    if not all(0 < hole['x_mm'] < w and 0 < hole['y_mm'] < h for hole in mounts):
        raise ValueError('Mounting centers outside panel')
    if w > 70 or h > 165:
        raise ValueError('Panel no longer fits this A4 layout; adjust drawing placement')
    pcb_bottom = next(hole['y_mm'] for hole in p['holes'] if hole['id'] == 'AmplifierPowerLED') + p['pcb_installation']['amplifier_led_center_to_bottom_mm']
    overlap = max(0, pcb_bottom - (y + wh))
    pdfmetrics.registerFont(TTFont('PanelTemplateCN', str(font)))
    output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output), pagesize=(210 * MM, 297 * MM))
    c.setTitle('旋钮面板木板开孔纸样 / A4 / 1:1')
    c.setAuthor('vinyl-record-player')
    c.setViewerPreference('PrintScaling', 'None')
    c.scale(MM, MM)

    # Paper coordinates use upper-left datum and increasing Y downward.
    def text(tx, ty, value, size=9, align='left'):
        c.setFont('PanelTemplateCN', size / MM)
        {'left': c.drawString, 'center': c.drawCentredString,
         'right': c.drawRightString}[align](tx, 297 - ty, value)

    def line(x1, y1, x2, y2, width=0.15):
        c.setLineWidth(width)
        c.line(x1, 297 - y1, x2, 297 - y2)

    def rect(rx, ry, rw, rh):
        c.rect(rx, 297 - ry - rh, rw, rh, stroke=1, fill=0)

    def hdim(x1, x2, dy, label):
        line(x1, dy, x2, dy)
        for xx in (x1, x2):
            line(xx - 0.7, dy - 1, xx + 0.7, dy + 1)
        text((x1 + x2) / 2, dy - 1.8, label, 8, 'center')

    def vdim(dx, y1, y2, label):
        line(dx, y1, dx, y2)
        for yy in (y1, y2):
            line(dx - 1, yy - 0.7, dx + 1, yy + 0.7)
        c.saveState()
        c.translate(dx - 2, 297 - (y1 + y2) / 2)
        c.rotate(90)
        c.setFont('PanelTemplateCN', 8 / MM)
        c.drawCentredString(0, 0, label)
        c.restoreState()

    ox, oy = 75, 48
    text(18, 18, '旋钮面板 · 木板开孔纸样', 17)
    text(18, 27, f'A4 竖向 / 1:1 / 单位 mm / 面板 {w:g} × {h:g} / 木板厚 {p["mounting"]["wood_thickness_mm"]:g}', 9)
    text(18, 34, '打印选“实际大小 / 100%”，关闭“适合页面”。此面朝箱体外侧。', 9)
    line(18, 38, 192, 38, 0.25)

    c.setStrokeGray(0.5)
    c.setDash(2, 1.5)
    c.setLineWidth(0.15)
    rect(ox, oy, w, h)
    c.setDash()
    c.setStrokeGray(0)
    hdim(ox, ox + w, oy - 4, f'{w:g} 面板外廓')
    vdim(ox + w + 8, oy, oy + h, f'{h:g} 面板外廓')
    text(ox - 2, oy + 3, '(0,0)', 8, 'right')
    text(18, 54, '基准：面板左上角', 9)
    text(18, 61, 'X 向右 / Y 向下', 8)
    text(18, 74, '虚线：面板定位外廓', 8)
    text(18, 81, '不沿虚线切木板', 8)
    text(18, 94, '实线：木板窗口', 8)
    text(18, 101, '锯缝留在去除区域内', 8)
    text(18, 114, '十字：固定孔中心', 8)
    text(18, 121, '仅定位，不指定钻径', 8)

    c.setLineWidth(0.25)
    rect(ox + x, oy + y, ww, wh)
    hdim(ox + x, ox + x + ww, oy + y + 11, f'{ww:g}')
    vdim(ox + x + 8, oy + y, oy + y + wh, f'{wh:g}')
    cx = ox + x + ww / 2
    text(cx + 2, oy + y + 55, '去除区域', 11, 'center')
    text(cx + 2, oy + y + 64, f'{ww:g} × {wh:g} mm', 9, 'center')
    text(cx + 2, oy + y + 73, '当前试排窗口', 8, 'center')
    text(cx + 2, oy + y + 82, '先核对 PCB 配合', 8, 'center')
    text(151, 59, '窗口边界坐标', 9)
    for i, value in enumerate([f'左 X={x:g}', f'右 X={x + ww:g}', f'上 Y={y:g}', f'下 Y={y + wh:g}']):
        text(151, 67 + i * 6, value, 8)
    text(151, 103, '固定中心坐标', 9)
    for i, hole in enumerate(mounts):
        hx, hy = hole['x_mm'], hole['y_mm']
        line(ox + hx - 2.5, oy + hy, ox + hx + 2.5, oy + hy, 0.2)
        line(ox + hx, oy + hy - 2.5, ox + hx, oy + hy + 2.5, 0.2)
        c.circle(ox + hx, 297 - oy - hy, 0.18, stroke=0, fill=1)
        text(151, 112 + i * 7, f'({hx:g}, {hy:g})', 8)
    text(151, 152, '螺杆 Ø3.2', 8)
    text(151, 159, '面板孔 Ø3.5', 8)
    text(151, 166, '木板导孔另定', 8)
    text(ox + w / 2, oy + h + 5, '按虚线定位面板安装位置', 8, 'center')

    text(18, 223, '使用：核对标尺 → 沿虚线裁纸并定位 → 标记实线及四个十字中心。', 9)
    text(18, 230, '木板导孔按螺丝牙型与木材确定；面板 Ø3.5 孔不是木板导孔规格。', 8)
    if overlap:
        text(18, 237, f'配合未确认：PCB 下缘 Y={pcb_bottom:g}，与窗口下方木条有 {overlap:g} mm 投影重叠；挖孔前试装。', 8)
    else:
        text(18, 237, '窗口与 PCB 实际深度位置未确认；挖孔前用实物试装。', 8)
    c.setLineWidth(0.2)
    rect(18, 242, 50, 50)
    text(43, 264, '50 × 50 mm', 9, 'center')
    text(43, 272, '横竖校验方框', 8, 'center')
    hdim(85, 185, 258, '100 mm 打印校验线')
    for xx in range(85, 186, 10):
        line(xx, 256.5, xx, 259.5, 0.2)
    text(85, 274, '用尺确认：横向 100 mm，方框横竖各 50 mm。', 8)
    text(85, 281, '若尺寸不符，调整打印缩放后重新打印。', 8)
    text(85, 290, '来源：cad/control-panel.json / 正面视图，无镜像。', 7)
    c.showPage()
    c.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', type=Path, required=True,
                        help='Embeddable Chinese TrueType font')
    args = parser.parse_args()
    p = json.loads((ROOT / 'cad/control-panel.json').read_text())
    export_template(p, ROOT / 'output/pdf/control-panel-cutting-template-A4.pdf', args.font)


if __name__ == '__main__':
    main()
