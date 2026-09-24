"""Compose the numbered CAD assembly guide; requires reportlab and a CJK font."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

ROOT = Path(__file__).resolve().parents[1]
MM = 72/25.4
WIDTH, HEIGHT = 594, 420
COLORS = {'W': '#956233', 'F': '#596C79', 'C': '#557787',
          'K': '#355E79', 'S': '#89659C', 'A': '#277C98', 'E': '#288068'}
INK, MUTED = '#20313B', '#62747E'


def number(value):
    return f'{value:.3f}'.rstrip('0').rstrip('.')


def validate_annotations(data):
    shown = {'overview': {e['code'] for e in data['entries'] if e['page'] == 1},
             'exploded': {e['code'] for e in data['entries'] if e['page'] == 2} - {'W04', 'E05', 'E06'},
             'rear': {'W04', 'E05', 'E06', 'A03'}}
    for key, codes in shown.items():
        view = data['views'][key]
        missing = codes-set(view['anchors'])
        occluded = codes & set(view['occluded_by'])
        if missing or occluded:
            raise ValueError(f'Unusable annotations in {key}: missing={missing}, occluded={occluded}')


class Guide:
    def __init__(self, root, data, output, font):
        self.root, self.data = root, data
        pdfmetrics.registerFont(TTFont('GuideCJK', str(font)))
        self.c = canvas.Canvas(str(output), pagesize=(WIDTH*MM, HEIGHT*MM))
        self.c.setTitle('黑胶唱片机 / 整机全景与组件导览')
        self.c.setAuthor('vinyl-record-player / FreeCAD')

    def text(self, x, y, value, size=10, color=INK):
        self.c.setFillColor(HexColor(color))
        self.c.setFont('GuideCJK', size)
        self.c.drawString(x*MM, (HEIGHT-y)*MM, str(value))

    def line(self, x1, y1, x2, y2, color='#DBE3E6', width=0.5):
        self.c.setStrokeColor(HexColor(color)); self.c.setLineWidth(width)
        self.c.line(x1*MM, (HEIGHT-y1)*MM, x2*MM, (HEIGHT-y2)*MM)

    def wrap(self, value, width, size):
        lines, line = [], ''
        for char in value:
            if pdfmetrics.stringWidth(line+char, 'GuideCJK', size) > width*MM:
                lines.append(line); line = char
            else:
                line += char
        return lines+[line]

    def badge(self, code, x, y):
        color = COLORS[code[0]]
        self.c.setFillColor(HexColor(color))
        self.c.roundRect((x-6.3)*MM, (HEIGHT-y-3.2)*MM, 12.6*MM, 6.4*MM, 1.7*MM, stroke=0, fill=1)
        self.text(x-4.8, y+1.1, code, 8.4, '#FFFFFF')

    def start(self, page, title, subtitle):
        self.text(16, 19, '黑胶唱片机', 24)
        self.text(64, 19, '/  整机结构导览', 17)
        self.text(16, 31, title, 14)
        self.text(16, 40, subtitle, 9.5, MUTED)
        self.text(472, 18, f'G-0{page}   /   A2 横向   /   {page:02} — 02', 10, MUTED)
        self.line(16, 45, 578, 45, INK, 0.8)
        self.line(16, 403, 578, 403, INK)
        self.text(16, 411, f'{self.data["revision"]}  ·  当前弯臂机芯装配  ·  示意视图不按比例量取', 8.5, MUTED)
        self.text(330, 411, '实体位置与图册关联来自保存 CAD；采购件／接口待确认，非制造或接线放行图。', 8.5, MUTED)

    def image(self, key, rect):
        view = self.data['views'][key]
        x, y, w, h = rect
        left, top, right, bottom = view['content_box']
        scale = min(w/(right-left), h/(bottom-top))
        ox = x+(w-(right-left)*scale)/2-left*scale
        oy = y+(h-(bottom-top)*scale)/2-top*scale
        self.c.saveState()
        clip = self.c.beginPath()
        clip.rect(x*MM, (HEIGHT-y-h)*MM, w*MM, h*MM)
        self.c.clipPath(clip, stroke=0)
        self.c.drawImage(str(self.root/view['image']), ox*MM, (HEIGHT-oy-scale)*MM,
                         scale*MM, scale*MM, mask='auto')
        self.c.restoreState()
        return {code: (ox+u*scale, oy+v*scale) for code, (u, v) in view['anchors'].items()}

    def balloons(self, anchors, left_codes, right_codes, left_x, right_x, y0, step):
        # Each side is sorted vertically by its real projected anchor. This
        # keeps the fan-out deterministic and avoids crossing parallel leaders.
        for codes, x in [(left_codes, left_x), (right_codes, right_x)]:
            for i, code in enumerate(sorted(codes, key=lambda c: anchors[c][1])):
                ax, ay = anchors[code]
                by = y0+i*step
                edge = x+6.3 if x < ax else x-6.3
                elbow = edge+5 if x < ax else edge-5
                self.line(ax, ay, elbow, by, COLORS[code[0]], 0.7)
                self.line(elbow, by, edge, by, COLORS[code[0]], 0.7)
                self.c.setFillColor(HexColor(COLORS[code[0]]))
                self.c.circle(ax*MM, (HEIGHT-ay)*MM, 0.8*MM, fill=1, stroke=0)
                self.badge(code, x, by)

    def legend(self, page, x, y, width, step):
        self.text(x, y, '编号 / 部件与材料', 12)
        self.text(x+width-53, y, '数量 · 关联图号', 9, MUTED)
        y += 9
        for entry in [e for e in self.data['entries'] if e['page'] == page]:
            code = entry['code']
            self.badge(code, x+6.3, y+1)
            self.text(x+16, y+2, entry['title'], 10.2)
            self.text(x+width-43, y+2, entry['quantity'], 8.5, MUTED)
            material = entry['material']
            if 'stock_mm' in entry:
                material += '；备料 '+' × '.join(number(n) for n in entry['stock_mm'])+' mm'
            lines = self.wrap(material, width-16, 8.1)
            for j, text in enumerate(lines):
                self.text(x+16, y+6+j*3.5, text, 8.1, MUTED)
            refs = ' / '.join(entry['drawings'])
            self.text(x+16, y+6+len(lines)*3.5, '详图 '+refs, 8.1, COLORS[code[0]])
            if 6+len(lines)*3.5+2 >= step:
                raise ValueError('Legend row overflow: '+code)
            self.line(x, y+step-3, x+width, y+step-3)
            y += step

    def make(self):
        self.start(1, '01  从整机外观认识部件',
                   '开盖三维全景  /  同色编号对应右侧目录  /  内部结构见第 2 页')
        anchors = self.image('overview', (46, 66, 285, 289))
        self.balloons(anchors, ['C01', 'W02', 'F01', 'K02', 'K03', 'E01', 'C03'],
                      ['C02', 'W01', 'K01', 'K04', 'K05', 'K06', 'K07', 'K08'],
                      25, 363, 82, 35)
        self.legend(1, 391, 58, 185, 21)
        dims = ' × '.join(number(n) for n in self.data['nominal_cabinet_mm'])
        self.text(47, 372, '木箱与闭盖名义外廓  '+dims+' mm', 11)
        self.text(47, 380, '合页与 AC 插座法兰超出后板；含合页外廓见 A-01。机芯安装尺寸仍待确认。', 9, MUTED)
        self.text(47, 390, '读图路径：定位编号 → 查看材料与数量 → 按 A / B / C 图号查尺寸。', 9, MUTED)
        self.c.showPage()

        self.start(2, '02  分层展开，认识内部结构',
                   '板件仅为展示而移开，零件尺寸未缩放  /  图中层间距离不是安装间隙或拆装顺序')
        anchors = self.image('exploded', (53, 62, 273, 261))
        left = ['W03', 'W06', 'W10', 'F02', 'F03', 'S01', 'E03', 'E04', 'S02']
        right = [e['code'] for e in self.data['entries'] if e['page'] == 2
                 and e['code'] not in left+['W04', 'E05', 'E06']]
        self.balloons(anchors, left, right, 25, 363, 62, 24)
        self.legend(2, 391, 55, 185, 16)
        self.line(16, 329, 376, 329)
        self.text(20, 337, '后部接口定位（后板半透明）', 10)
        rear = self.image('rear', (36, 347, 149, 39))
        self.balloons(rear, ['E05', 'A03'], ['W04', 'E06'], 24, 198, 353, 26)
        self.text(219, 345, '材料与范围说明', 10)
        notes = ['木色：木板／饰面；蓝色：音响与机芯；绿色：电子模块。',
                 '颜色用于识别类别，不代表最终材质或采购状态。',
                 f'覆盖 {self.data["physical_object_count"]} 个物理 CAD 对象；复合件、重复件合并标注。',
                 '电源线、内部线束、LED 灯带、紧固／密封／吸音材料',
                 '尚未建模；不虚构其位置、数量或采购规格。',
                 '备用电子区与接口板为预留，不代表已购模块。']
        for i, note in enumerate(notes):
            self.text(219, 352+i*5, note, 8.1, MUTED)
        self.text(20, 397, 'A = 图册 01 整机与外壳    B = 图册 02 音腔与内部结构    C = 图册 03 机芯与电子部件；按图号查找完整尺寸。', 8.2, MUTED)
        self.c.showPage()
        self.c.save()


def make(root=ROOT, font=Path('/Users/miclle/Library/Fonts/AlibabaPuHuiTi-2-55-Regular.ttf')):
    root = Path(root)
    data = json.loads((root/'tmp/assembly-guide/manifest.json').read_text())
    validate_annotations(data)
    for name, digest in data['sources'].items():
        if hashlib.sha256((root/'cad'/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Guide views are stale; rerun assembly-guide.FCMacro')
    out = root/'output/pdf/00-assembly-guide.pdf'
    out.parent.mkdir(parents=True, exist_ok=True)
    Guide(root, data, out, font).make()
    index = {k: v for k, v in data.items() if k != 'views'}
    (root/'cad/assembly-guide-index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2)+'\n')
    renderer = shutil.which('pdftoppm')
    if not renderer:
        raise RuntimeError('Install Poppler (pdftoppm) to export the two guide PNGs')
    (root/'previews').mkdir(parents=True, exist_ok=True)
    subprocess.run([renderer, '-r', '180', '-png', str(out),
                    str(root/'previews/assembly-guide')], check=True)
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', type=Path, default=Path('/Users/miclle/Library/Fonts/AlibabaPuHuiTi-2-55-Regular.ttf'))
    args = parser.parse_args()
    print(make(font=args.font))
