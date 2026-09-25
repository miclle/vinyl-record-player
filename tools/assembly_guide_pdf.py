"""Compose the numbered CAD assembly guide; requires reportlab and a CJK font."""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from wood_stock import RETIRED_WOOD_CODES

ROOT = Path(__file__).resolve().parents[1]
MM = 72/25.4
WIDTH, HEIGHT = 594, 420
CONTENT_LEFT, CONTENT_RIGHT = 16, 578
VISUAL_RIGHT = 376
MAIN_VIEW_X, MAIN_VIEW_WIDTH = 46, 285
CALLOUT_LEFT_X, CALLOUT_RIGHT_X = 25, 363
LEGEND_X, LEGEND_WIDTH = 391, 185
COLORS = {'W': '#956233', 'F': '#596C79', 'C': '#557787',
          'K': '#355E79', 'S': '#89659C', 'A': '#277C98', 'E': '#288068'}
INK, MUTED = '#20313B', '#62747E'
EMBEDDED_GUIDE_MARKER = NameObject('/VinylAssemblyGuidePage')
BOOK_01_BASE_CODES = (
    'A-00', 'A-STOCK', 'A-01', 'A-02', 'A-03',
    'A-P01', 'A-P02', 'A-P03', 'A-P04', 'A-P05', 'A-P06', 'A-P07', 'A-P08',
    'A-H01', 'A-H02', 'A-H03', 'A-POS',
)


def number(value):
    return f'{value:.3f}'.rstrip('0').rstrip('.')


def validate_annotations(data):
    wood_entries = [entry for entry in data['entries'] if entry['code'].startswith('W')]
    if not wood_entries or any('stock_count' not in entry for entry in wood_entries):
        raise ValueError('Guide catalog is stale; rerun assembly-guide.FCMacro')
    shown = {'overview': {e['code'] for e in data['entries'] if e['page'] == 1},
             'exploded': {e['code'] for e in data['entries'] if e['page'] == 2} - {'W04', 'E05', 'E06'},
             'rear': {'W04', 'E05', 'E06', 'A03'}}
    for key, codes in shown.items():
        view = data['views'][key]
        missing = codes-set(view['anchors'])
        occluded = codes & set(view['occluded_by'])
        if missing or occluded:
            raise ValueError(f'Unusable annotations in {key}: missing={missing}, occluded={occluded}')


def embed_guide_in_book(guide_path, book_path, output_path=None,
                        expected_source_sha256=None, expected_base_codes=None):
    """Insert the two original-size guide pages after A-STOCK, idempotently."""
    guide_path, book_path = Path(guide_path), Path(book_path)
    output_path = Path(output_path) if output_path else book_path
    if not book_path.exists():
        raise FileNotFoundError(
            f'Missing {book_path.name}; generate the drawing pack before the assembly guide'
        )
    guide = PdfReader(guide_path)
    if len(guide.pages) != 2:
        raise ValueError(f'Expected two assembly-guide pages, found {len(guide.pages)}')
    for page, code in zip(guide.pages, ('G-01', 'G-02')):
        if code not in (page.extract_text() or ''):
            raise ValueError(f'Assembly-guide page is missing {code}')

    book = PdfReader(book_path)
    clean_pages = [i for i, page in enumerate(book.pages)
                   if not bool(page.get(EMBEDDED_GUIDE_MARKER, False))]
    if expected_base_codes:
        if len(clean_pages) != len(expected_base_codes):
            raise ValueError(
                f'Book 01 has {len(clean_pages)} base pages, expected '
                f'{len(expected_base_codes)}; regenerate the drawing pack'
            )
        for source_index, code in zip(clean_pages, expected_base_codes):
            if code not in (book.pages[source_index].extract_text() or ''):
                raise ValueError(
                    f'Book 01 base page sequence is stale at {code}; '
                    'regenerate the drawing pack'
                )
    if expected_source_sha256:
        first_page_text = book.pages[clean_pages[0]].extract_text() or ''
        if expected_source_sha256 not in first_page_text:
            raise ValueError(
                'Book 01 source CAD hash differs from the assembly guide; '
                'regenerate the drawing pack'
            )
    stock_pages = [position for position, source_index in enumerate(clean_pages)
                   if 'A-STOCK' in (book.pages[source_index].extract_text() or '')]
    if len(stock_pages) != 1:
        raise ValueError(f'Expected one A-STOCK page, found {len(stock_pages)}')
    insert_at = stock_pages[0] + 1

    outlines_by_page = {}
    def collect_outlines(items):
        for item in items:
            if isinstance(item, list):
                collect_outlines(item)
                continue
            page_number = book.get_destination_page_number(item)
            if page_number in clean_pages:
                outlines_by_page.setdefault(page_number, []).append(item.title)
    collect_outlines(book.outline)

    writer = PdfWriter()
    writer.append(book, pages=clean_pages, import_outline=False)
    writer.merge(insert_at, guide, import_outline=False)
    for page in writer.pages[insert_at:insert_at + len(guide.pages)]:
        page[EMBEDDED_GUIDE_MARKER] = BooleanObject(True)
    output_index = 0
    for source_index in clean_pages:
        if output_index == insert_at:
            writer.add_outline_item('G-01  整机外观导览', output_index)
            writer.add_outline_item('G-02  内部结构导览', output_index + 1)
            output_index += len(guide.pages)
        for title in outlines_by_page.get(source_index, []):
            writer.add_outline_item(title, output_index)
        output_index += 1
    if book.metadata:
        writer.add_metadata({key: str(value) for key, value in book.metadata.items()
                             if value is not None})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name('.' + output_path.name + '.tmp')
    try:
        with temporary.open('wb') as stream:
            writer.write(stream)
        combined = PdfReader(temporary)
        expected_pages = len(clean_pages) + len(guide.pages)
        if len(combined.pages) != expected_pages:
            raise ValueError(
                f'Combined drawing book has {len(combined.pages)} pages, expected {expected_pages}'
            )
        embedded = combined.pages[insert_at:insert_at + len(guide.pages)]
        if not all(bool(page.get(EMBEDDED_GUIDE_MARKER, False)) for page in embedded):
            raise ValueError('Combined drawing book lost its embedded-guide markers')
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return expected_pages


class Guide:
    def __init__(self, root, data, output, font):
        self.root, self.data = root, data
        self.entries_by_code = {entry['code']: entry for entry in data['entries']}
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

    def callout_name(self, code, x, y, width=28):
        title = self.entries_by_code[code]['title']
        size = 7.8
        lines = self.wrap(title, width, size)
        if len(lines) > 2:
            raise ValueError('Callout name overflow: '+code)
        for i, line in enumerate(lines):
            line_width = pdfmetrics.stringWidth(line, 'GuideCJK', size)/MM
            self.text(x-line_width/2, y+6.3+i*3.2, line, size, INK)

    def start(self, page, title, subtitle):
        self.text(CONTENT_LEFT, 19, '黑胶唱片机', 24)
        self.text(64, 19, '/  整机结构导览', 17)
        self.text(CONTENT_LEFT, 31, title, 14)
        self.text(CONTENT_LEFT, 40, subtitle, 9.5, MUTED)
        self.text(472, 18, f'G-0{page}   /   A2 横向   /   {page:02} — 02', 10, MUTED)
        self.line(CONTENT_LEFT, 45, CONTENT_RIGHT, 45, INK, 0.8)
        self.line(CONTENT_LEFT, 403, CONTENT_RIGHT, 403, INK)
        self.text(CONTENT_LEFT, 411, f'{self.data["revision"]}  ·  当前弯臂机芯装配  ·  示意视图不按比例量取', 8.5, MUTED)
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

    def balloons(self, anchors, left_codes, right_codes, left_x, right_x, y0, step,
                 show_names=False, name_width=28):
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
                if show_names:
                    self.callout_name(code, x, by, name_width)

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
                   '开盖三维全景  /  编号下方直读名称  /  完整材料与详图见右侧目录')
        anchors = self.image('overview', (MAIN_VIEW_X, 66, MAIN_VIEW_WIDTH, 289))
        self.balloons(anchors, ['C01', 'W02', 'F01', 'K02', 'K03', 'E01', 'C03'],
                      ['C02', 'W01', 'K01', 'K04', 'K05', 'K06', 'K07', 'K08'],
                      CALLOUT_LEFT_X, CALLOUT_RIGHT_X, 82, 35, show_names=True)
        self.legend(1, LEGEND_X, 58, LEGEND_WIDTH, 21)
        dims = ' × '.join(number(n) for n in self.data['nominal_cabinet_mm'])
        self.text(47, 372, '木箱与闭盖名义外廓  '+dims+' mm', 11)
        self.text(47, 380, '合页与 AC 插座法兰超出后板；含合页外廓见 A-01。机芯安装尺寸仍待确认。', 9, MUTED)
        stock_total = sum(entry.get('stock_count', 0) for entry in self.data['entries'])
        self.text(47, 388, f'木板矩形备料合计 {stock_total} 块／条；完整加工说明见图册 01 / A-STOCK。', 9, MUTED)
        self.text(47, 396, f'W05 已退役：{RETIRED_WOOD_CODES["W05"]}', 8.5, MUTED)
        self.c.showPage()

        self.start(2, '02  分层展开，认识内部结构',
                   '分层仅为展示  /  编号下方直读名称  /  层间距离不是安装间隙或拆装顺序')
        anchors = self.image('exploded', (MAIN_VIEW_X, 62, MAIN_VIEW_WIDTH, 261))
        left = ['W03', 'W06', 'W10', 'F02', 'F03', 'S01', 'E03', 'E04', 'S02']
        right = [e['code'] for e in self.data['entries'] if e['page'] == 2
                 and e['code'] not in left+['W04', 'E05', 'E06']]
        self.balloons(anchors, left, right, CALLOUT_LEFT_X, CALLOUT_RIGHT_X, 62, 24,
                      show_names=True)
        self.legend(2, LEGEND_X, 55, LEGEND_WIDTH, 16)
        self.line(CONTENT_LEFT, 329, VISUAL_RIGHT, 329)
        self.text(20, 337, '后部接口定位（后板半透明）', 10)
        rear = self.image('rear', (36, 347, 149, 39))
        self.balloons(rear, ['E05', 'A03'], ['W04', 'E06'], 24, 198, 353, 26,
                      show_names=True)
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
    source_sha256 = data['sources'].get('record-player.FCStd')
    if not source_sha256:
        raise ValueError('Guide manifest is missing the record-player.FCStd source hash')
    renderer = shutil.which('pdftoppm')
    if not renderer:
        raise RuntimeError('Install Poppler (pdftoppm) to export the two guide PNGs')
    guide_pdf = root/'tmp/assembly-guide/guide-pages.pdf'
    guide_pdf.parent.mkdir(parents=True, exist_ok=True)
    try:
        Guide(root, data, guide_pdf, font).make()
        combined_book = root/'output/pdf/01-assembly-and-enclosure.pdf'
        with tempfile.TemporaryDirectory(prefix='assembly-guide-publish-',
                                         dir=root/'tmp') as stage_name:
            stage = Path(stage_name)
            staged_book = stage/combined_book.name
            combined_pages = embed_guide_in_book(
                guide_pdf, combined_book, output_path=staged_book,
                expected_source_sha256=source_sha256,
                expected_base_codes=BOOK_01_BASE_CODES,
            )
            if combined_pages != 19:
                raise ValueError(
                    f'Combined drawing book has {combined_pages} pages, expected 19'
                )
            index = {k: v for k, v in data.items() if k != 'views'}
            index['embedded_in'] = {'file': combined_book.name, 'after': 'A-STOCK',
                                    'pages': combined_pages}
            staged_index = stage/'assembly-guide-index.json'
            staged_index.write_text(json.dumps(index, ensure_ascii=False, indent=2)+'\n')
            preview_prefix = stage/'assembly-guide'
            subprocess.run([renderer, '-r', '180', '-png', str(guide_pdf),
                            str(preview_prefix)], check=True)
            staged_previews = [stage/f'assembly-guide-{page}.png' for page in (1, 2)]
            if not all(path.is_file() and path.stat().st_size for path in staged_previews):
                raise ValueError('Poppler did not produce both assembly-guide preview PNGs')

            final_index = root/'cad/assembly-guide-index.json'
            final_previews = [root/f'previews/assembly-guide-{page}.png'
                              for page in (1, 2)]
            final_index.parent.mkdir(parents=True, exist_ok=True)
            final_previews[0].parent.mkdir(parents=True, exist_ok=True)
            staged_book.replace(combined_book)
            staged_index.replace(final_index)
            for staged, final in zip(staged_previews, final_previews):
                staged.replace(final)
        (root/'output/pdf/00-assembly-guide.pdf').unlink(missing_ok=True)
        return combined_book
    finally:
        guide_pdf.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', type=Path, default=Path('/Users/miclle/Library/Fonts/AlibabaPuHuiTi-2-55-Regular.ttf'))
    args = parser.parse_args()
    print(make(font=args.font))
