"""Compose three A3 vector PDF drawing books from drawing_data.py output.

Requires reportlab and svglib in a regular Python environment. FreeCAD is only
needed for the preceding extraction stage. All dimensions are in millimetres.
"""
import argparse
import io
import json
import math
from datetime import date
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg
from drawing_detail_pages import hole_sheet_page, section_page

ROOT=Path(__file__).resolve().parents[1]
MM=72/25.4
PAGE_W,PAGE_H=420,297
INK='#1E2930'
DIM='#805536'
MUTED='#64727B'
LIGHT='#D5DDE0'
VIEW_LABELS={'baffle_face':'前表面法向 / X-S','top':'俯视 / X-Y','front':'正视 / X-Z','right':'右视 / Y-Z',
             'rear':'后视 / -X-Z','left':'左视 / -Y-Z','bottom':'仰视 / X--Y'}
VIEW_AXES={'baffle_face':('X','S'),'top':('X','Y'),'front':('X','Z'),'right':('Y','Z'),
           'rear':('X','Z'),'left':('Y','Z'),'bottom':('X','Y')}


def num(n):
    return f'{n:.3f}'.rstrip('0').rstrip('.')


def load_projection(view):
    drawing=svg2rlg(io.BytesIO(view['svg'].encode()))
    # svglib interprets SVG pixels at 96 dpi; restore model mm before scaling
    # to the paper. Otherwise geometry is 25% smaller than its dimensions.
    w,h=view['size_mm']
    drawing.scale(w/drawing.width,h/drawing.height)
    return drawing


class Book:
    def __init__(self,path,title,data,font):
        self.path=path
        self.title=title
        self.data=data
        self.font=font
        self.c=canvas.Canvas(str(path),pagesize=(PAGE_W*MM,PAGE_H*MM),pageCompression=1)
        self.c.setTitle('LUMI / '+title)
        self.c.setAuthor('vinyl-record-player / CAD drawing export')
        self.page=0
        self.index=[]

    def text(self,x,y,text,size=9,color=INK,align='left'):
        c=self.c
        c.setFillColor(HexColor(color));c.setFont(self.font,size)
        fn={'left':c.drawString,'center':c.drawCentredString,'right':c.drawRightString}[align]
        fn(x*MM,(PAGE_H-y)*MM,str(text))

    def line(self,x1,y1,x2,y2,color=LIGHT,width=0.3):
        self.c.setStrokeColor(HexColor(color));self.c.setLineWidth(width)
        self.c.line(x1*MM,(PAGE_H-y1)*MM,x2*MM,(PAGE_H-y2)*MM)

    def rect(self,x,y,w,h,color=LIGHT):
        self.c.setStrokeColor(HexColor(color));self.c.setLineWidth(0.35)
        self.c.rect(x*MM,(PAGE_H-y-h)*MM,w*MM,h*MM,fill=0,stroke=1)

    def wrap(self,text,width,size):
        lines=[];line=''
        for char in text:
            if pdfmetrics.stringWidth(line+char,self.font,size)>width*MM:
                lines.append(line);line=char
            else: line+=char
        if line:lines.append(line)
        return lines

    def paragraph(self,x,y,text,width,size=9,color=INK,leading=4):
        for line in self.wrap(text,width,size):
            self.text(x,y,line,size,color);y+=leading
        return y

    def start(self,title,code,subtitle=''):
        self.page+=1
        self.index.append((self.page,title,code))
        self.c.bookmarkPage(code)
        self.c.addOutlineEntry(f'{code}  {title}',code,level=0)
        self.text(12,14,'LUMI  /  '+self.title,16)
        self.text(408,14,f'{code}  |  A3 横向  |  单位 mm',9,MUTED,'right')
        self.text(12,23,title,11)
        if subtitle:self.text(408,23,subtitle,8,MUTED,'right')
        self.line(12,27,408,27,INK,0.65)
        self.line(12,284,408,284,INK,0.5)
        self.text(12,290,'现存 CAD 几何尺寸 / 概念与空间核对图；未定义公差、连接工艺和安装孔不作加工放行。',8,MUTED)
        self.text(408,290,f'{self.data["revision"]}  |  {date.today().isoformat()}  |  {self.page:02}',8,MUTED,'right')

    def end(self):self.c.showPage()
    def save(self):self.c.save()

    def hdim(self,x,y,w,label,edge):
        self.line(x,edge,x,y+2,DIM);self.line(x+w,edge,x+w,y+2,DIM)
        self.line(x,y,x+w,y,DIM,0.45)
        for xx in (x,x+w):self.line(xx-0.8,y+1,xx+0.8,y-1,DIM,0.55)
        self.text(x+w/2,y-1.3,label,8,DIM,'center')

    def vdim(self,x,y,h,label,edge):
        self.line(edge,y,x+2,y,DIM);self.line(edge,y+h,x+2,y+h,DIM)
        self.line(x,y,x,y+h,DIM,0.45)
        for yy in (y,y+h):self.line(x-1,yy+0.8,x+1,yy-0.8,DIM,0.55)
        if h<8:
            self.text(x-2,y+h/2+1,label,7,DIM,'right')
            return
        c=self.c;c.saveState();c.translate((x-1.5)*MM,(PAGE_H-y-h/2)*MM);c.rotate(90)
        c.setFont(self.font,8);c.setFillColor(HexColor(DIM));c.drawCentredString(0,0,label);c.restoreState()

    def view(self,view,key,x,y,w,h,dimension=True,forced_scale=None):
        vw,vh=view['size_mm']
        fit=min((w-25)/max(vw,0.01),(h-23)/max(vh,0.01))
        scales=[0.05,0.1,0.125,0.2,0.25,1/3,0.5,1,2,4]
        scale=forced_scale or max((s for s in scales if s<=fit+1e-8),default=fit)
        dw,dh=vw*scale,vh*scale
        ox=x+(w-dw)/2+4;oy=y+9+(h-23-dh)/2
        ratio=f'{num(scale)}:1' if scale>=1 else f'1:{num(1/scale)}'
        self.text(x+2,y+3,VIEW_LABELS[key]+'   '+ratio,8,MUTED)
        self.projection(view,ox,oy,scale)
        if dimension:
            ha,va=VIEW_AXES[key]
            self.hdim(ox,oy+dh+7,dw,f'{ha} {num(vw)}',oy+dh)
            self.vdim(ox-7,oy,dh,f'{va} {num(vh)}',ox)
        return ox,oy,scale

    def projection(self,view,ox,oy,scale):
        drawing=load_projection(view)
        # SVG units are model mm. Compensate stroke width for paper readability.
        def stroke(node):
            if hasattr(node,'strokeWidth') and node.strokeWidth is not None:
                node.strokeWidth=0.17/scale
            for child in getattr(node,'contents',[]):stroke(child)
        stroke(drawing)
        self.c.saveState()
        self.c.translate(ox*MM,(PAGE_H-oy-view["size_mm"][1]*scale)*MM)
        self.c.scale(scale*MM,scale*MM)
        renderPDF.draw(drawing,self.c,0,0)
        self.c.restoreState()

    def card(self,card,x,y,w=194):
        self.rect(x,y,w,246)
        title=card['title'].split(' · ')[0]
        self.text(x+5,y+7,title,11)
        self.text(x+5,y+13,card['key']+f'   数量 {card["quantity"]}',8,MUTED)
        refs={'Bottom':'A-H01','Back':'A-H02','Baffle':'B-H01 / A-03','AcousticRoof':'B-H02','FloatingDeck':'B-H03'}
        if card['key'] in refs:
            self.text(x+w-5,y+13,'开孔定位 '+refs[card['key']],8,DIM,'right')
        main=card['primary']
        ox,oy,scale=self.view(card['views'][main],main,x+5,y+19,w-10,100)
        for feature in card.get('holes',[]):
            cx=ox+feature['u_mm']*scale
            cy=oy+(card['views'][main]['size_mm'][1]-feature['v_mm'])*scale
            self.line(cx-2,cy,cx+2,cy,MUTED)
            self.line(cx,cy-2,cx,cy+2,MUTED)
            self.line(cx,cy,cx+7,cy-5,DIM)
            self.text(cx+8,cy-5,feature['label'],8,DIM)
        others=[v for v in ('top','front','right') if v!=main]
        for i,v in enumerate(others):
            self.view(card['views'][v],v,x+5+i*(w-10)/2,y+126,(w-10)/2,42)
        self.line(x+5,y+173,x+w-5,y+173)
        labels=['长 X / 左右','宽 Y / 前后','高 Z / 上下','厚度 / 说明']
        vals=[num(n) for n in card['size_mm']]+[num(card['thickness_mm']) if card['thickness_mm'] is not None else '见下方说明']
        for i,(label,value) in enumerate(zip(labels,vals)):
            xx=x+5+i*(w-10)/4
            self.text(xx,y+178,label,7.8,MUTED)
            self.text(xx,y+184,value,11)
        origin=', '.join(num(n) for n in card['origin_mm'])
        self.text(x+5,y+192,'实体最小角整机坐标 (X, Y, Z) = ('+origin+')',8,MUTED)
        yy=y+199
        if 'stock_mm' in card:
            self.text(x+5,yy,'矩形备料 L × W × T：'+' × '.join(num(n) for n in card['stock_mm'])+' mm',10,DIM)
            yy+=6
        for note in card['notes']:
            yy=self.paragraph(x+5,yy,note,w-10,8.5,INK,4)
        if yy>y+244:
            raise ValueError(f'Notes overflow: {card["key"]}: {yy-y}')


def assembly_page(book,assembly,views,title,code,notes):
    book.start(title,code,'可见轮廓正投影 / 视图各自标注比例')
    book.view(assembly['views'][views[0]],views[0],18,36,220,185)
    book.view(assembly['views'][views[1]],views[1],245,36,158,90)
    book.view(assembly['views'][views[2]],views[2],245,138,158,90)
    y=239
    for note in notes:
        y=book.paragraph(18,y,note,385,9,INK,4.8)
    book.end()


def intro(book,data):
    book.start('图册索引与读图约定','A-00','3 份 PDF / 当前保存模型 / 非展开下料图')
    book.text(18,43,'图册 01  整机与外壳',17)
    book.text(18,52,'闭盖六面图、障板局部剖视、外壳零件；底板与后板开孔定位图。',10)
    book.text(18,70,'图册 02  音腔与内部结构',17)
    book.text(18,79,'内部布置、斜障板与音腔结构；障板、音腔顶板和浮动底板开孔定位图。',10)
    book.text(18,97,'图册 03  机芯与电子部件',17)
    book.text(18,106,'扬声器、功放、变压器、电子预留、选定弯臂机芯；附基线通用机芯对照。',10)
    book.line(18,116,402,116)
    paragraphs=[
        '方向与尺寸：X 为左右方向，Y 为前后方向，Z 为高度；原点是机体左前方桌面基准。尺寸表中的长、宽、高均为装配姿态下的 XYZ 外包络，不自动按最大边排序。',
        '尺寸精度：所有轮廓直接投影自保存的 FreeCAD 实体；外包络使用 optimalBoundingBox(False) 精确读取，显示到 0.001 mm 仅为数值记录，不表示制造公差。',
        '备料与厚度：木板另列整数矩形备料 L × W × T；斜板需按成形轮廓修切。板厚按法向计，空心罩标壁厚；未知厚度明确注明。名义板厚须实测，锯缝、贴皮和装配余量另核。',
        '投影约定：这是独立命名的正投影视图集，布局不采用统一第一角或第三角排列；各视图比例单独注明。小件可放大，薄件侧视尺寸文字记录真实厚度。打印采用 A3、100% 实际大小。',
        '同形件：侧板、格栅、隔板、脚垫等用代表件图形加数量，安装位置见附表。左右后板及承托梁按独立实体分别出图，避免把跨空区包络当成单块尺寸。',
        '当前配置：整机六面图采用选定弯臂核对版；共用结构取基线同形实体。选定机芯安装未放行，355 × 280 × 45 为参考 / 假设包络，不能视为已确认供应商尺寸。',
    ]
    y=127
    for paragraph in paragraphs:
        y=book.paragraph(18,y,paragraph,384,10,INK,5)+5
    book.text(18,244,f'覆盖核对：基线 {data["coverage"]["baseline_count"]} 个实体对象；选定机芯版 {data["coverage"]["study_count"]} 个实体对象；诊断干涉体不列作零件。',9)
    y=255
    for name,sha in data['sources'].items():
        book.text(18,y,name+'  SHA-256',8,MUTED)
        book.text(18,y+5,sha,8,MUTED);y+=13
    book.end()


def positions_page(book,cards,code,title):
    book.start(title,code,'同形代表件的各安装位置 / 单位 mm')
    book.text(18,39,'坐标为每个对象精确外包络的最小角；圆柱的坐标是包络角，不是轴心。',10)
    headers=[(18,'对象 ID'),(77,'零件'),(194,'X 最小'),(236,'Y 最小'),(278,'Z 最小'),(329,'数量 / 备注')]
    for x,label in headers:book.text(x,50,label,9,MUTED)
    y=58
    for card in cards:
        if card['quantity']<=1:continue
        for name,pos in card['positions_mm'].items():
            book.line(18,y+2,402,y+2)
            book.text(18,y,name,9)
            book.text(77,y,card['title'].split(' · ')[0],9)
            for x,n in zip((194,236,278),pos):book.text(x,y,num(n),9)
            book.text(329,y,'同形件 / 详见代表件图',8,MUTED)
            y+=8
    if y>280:raise ValueError('Position table overflow')
    book.end()


def stock_page(book,data):
    book.start('木板矩形备料汇总','A-STOCK','整数名义尺寸 / 成形与接口尺寸详见零件页')
    rows={}
    for card in data['cards']:
        if 'stock_mm' not in card:continue
        key=card['ids'][0]
        if key not in rows:rows[key]=[card,0]
        rows[key][1]+=card['quantity']
    for x,label in [(18,'板件'),(116,'数量'),(141,'备料长 L'),(177,'备料宽 W'),(213,'板厚 T'),(253,'后续加工')]:
        book.text(x,43,label,10,MUTED)
    y=55
    labels={'SideLeft':'左右侧板','AcousticDividerLeft':'左右低音隔板','Slat01':'横向木格栅条'}
    for key,(card,quantity) in rows.items():
        title=labels.get(key,card['title'].split(' · ')[0].split(' / ')[0])
        book.line(18,y+7,402,y+7)
        if key=='Baffle':title+='（B-H01 / A-03）'
        book.text(18,y,title,9)
        book.text(116,y,str(quantity),10)
        for x,value in zip((141,177,213),card['stock_mm']):book.text(x,y,num(value),11,DIM)
        book.paragraph(253,y,card['stock_note'],147,8,INK,4)
        y+=14
    y=max(y+10,228)
    for note in [
        f'共 {sum(quantity for _,quantity in rows.values())} 块 / 条。L、W 为板件自身平面的矩形备料尺寸，T 为法向板厚；与装配包络 XYZ 不同。',
        '斜障板备料后修斜口，隔板备料后修斜前缘，顶板切 T 形轮廓；几何小数保留在成形图中，不能把接缝坐标逐项取整。',
        '名义板厚须实测；本表不含锯缝、打磨、贴皮、封边及拼接余量。材料、连接方式与公差确认后才能作最终下料放行。',
    ]:y=book.paragraph(18,y,note,384,9,INK,4.8)+3
    book.end()


def make_books(data,out,font):
    pdfmetrics.registerFont(TTFont('DrawingChinese',str(font)))
    out.mkdir(parents=True,exist_ok=True)
    assemblies={a['key']:a for a in data['assemblies']}
    titles={1:'整机与外壳',2:'音腔与内部结构',3:'机芯与电子部件'}
    names={1:'01-assembly-and-enclosure.pdf',2:'02-acoustic-and-structure.pdf',3:'03-mechanism-and-electronics.pdf'}
    summaries=[]
    p=data['parameters'];ac=p['acoustic']
    W,D,H=(p[k] for k in ('width','depth','cabinet_top'))
    roof_top=ac['roof_bottom_z']+ac['roof_thickness']
    for volume in (1,2,3):
        book=Book(out/names[volume],titles[volume],data,'DrawingChinese')
        prefix='ABC'[volume-1]
        cards=[c for c in data['cards'] if c['volume']==volume]
        if volume==1:
            intro(book,data)
            stock_page(book,data)
            assembly_page(book,assemblies['selected-closed'],['top','front','right'],'整机闭盖 / 俯、正、右视','A-01',[
                f'机壳名义长 X {num(W)} × 宽 Y {num(D)} × 高 Z {num(p["closed_height"])}；含 AC 法兰总深 {num(D+p["ac_inlet"]["flange_thickness"])}；木壳板厚 {num(p["wall"])}。',
                '障板位于前格栅与透声布后方，本页被遮挡；局部剖视见 A-03，开孔定位见第 02 册 B-H01。机芯见图册 03。',
                f'木壳底面 Z={num(p["foot_height"])}，壳体顶面 Z={num(H)}；盖底 Z={num(p["cover_bottom"])}，盖顶 Z={num(p["closed_height"])}；坐标均以桌面为 Z=0。'])
            assembly_page(book,assemblies['selected-closed'],['bottom','rear','left'],'整机闭盖 / 仰、后、左视','A-02',[
                '仰视包含底部朝下的低音单元；后视可见倒相管安装开口。',
                f'低音轴心 ({num(p["woofer"]["center_x"])}, {num(p["woofer"]["center_y"])}）；四脚轴心 X={num(p["feet"]["side_inset"])}/{num(W-p["feet"]["side_inset"])}，Y={num(p["feet"]["front_y"])}/{num(D-p["feet"]["rear_inset"])}。底板孔位见 A-H01。',
                '接口板目前无 RCA 等实际孔位；后板与所有固定孔须在零件实测后确认。'])
            section_page(book,data['baffle_section'],p)
        elif volume==2:
            assembly_page(book,assemblies['internal'],['top','front','right'],'三音腔与后部电子区 / 去盖内部布置','B-00',[
                '为读图隐藏两侧木板、后板、音腔顶板、前障板及两块全频腔后板；零件结构详见后页。',
                f'三音腔：左右前部密闭试验腔，中央贯通低音腔。隔板 X={" / ".join(num(n) for n in p["acoustic_divider_x"])}，厚 {num(ac["partition_thickness"])}；全频腔后板 Y={num(ac["satellite_rear_y"])}，厚 {num(ac["partition_thickness"])}。',
                f'顶板 Z={num(ac["roof_bottom_z"])}..{num(roof_top)}；底板上表面 Z={num(p["foot_height"]+p["wall"])}；后部电源和功放区与前部全频腔分隔。'])
        else:
            cfg=data['mechanism']
            assembly_page(book,assemblies['selected-kit'],['top','front','right'],'选定弯臂机芯 / 停放姿态','C-00',[
                f'参考平面包络 {num(cfg["nominal_width"])} × {num(cfg["nominal_depth"])}；假设下探深度 {num(cfg["underbody_depth_assumption"])}；唱盘 Ø{num(cfg["platter_diameter"])} × {num(cfg["platter_thickness"])}。',
                '上图投影是已建模的上部外观实体；不把矩形下探诊断包络当成实体机芯或零件。',
                f'安装面 Z={num(H)}；音腔顶板顶面 Z={num(roof_top)}，现有净深 {num(H-roof_top)}；假设下探多需 {num(max(0,cfg["underbody_depth_assumption"]-(H-roof_top)))}，真实安装方案尚未确认。'])
        for i in range(0,len(cards),2):
            page_title=' / '.join(c['title'].split(' · ')[0] for c in cards[i:i+2])
            book.start(page_title,f'{prefix}-P{i//2+1:02}','尺寸表：长 X / 宽 Y / 高 Z / 厚度')
            for j,card in enumerate(cards[i:i+2]):book.card(card,12+j*202,32)
            book.end()
        for sheet in data['hole_sheets']:
            if sheet['volume']==volume:
                hole_sheet_page(book,sheet)
        if any(c['quantity']>1 for c in cards):
            positions_page(book,cards,f'{prefix}-POS','同形零件安装位置表')
        if volume==3:
            generic=[c for c in data['cards'] if c['volume']==4]
            assembly_page(book,assemblies['generic'],['top','front','right'],'附录 / 基线通用机芯正投影','C-G01',[
                '此页为原三单元基线的通用机芯占位。当前选定弯臂装配已替换这些机芯部件，两组不是同时安装。',
                '基线唱盘 Ø300，唱臂轴距 200，有效臂长 218；不用于约束候选弯臂机芯。',
                '下页按对象列出全部基线机芯 XYZ 包络；这些外观占位未定义真实壁厚和制造接口。'])
            book.start('附录 / 基线通用机芯尺寸记录','C-G02','装配姿态包络 / 厚度未知或实心占位')
            for x,label in [(18,'ID'),(83,'零件'),(234,'长 X'),(267,'宽 Y'),(300,'高 Z'),(335,'厚度状态')]:book.text(x,42,label,9,MUTED)
            y=54
            for c in generic:
                book.line(18,y+3,402,y+3)
                book.text(18,y,c['key'],8)
                book.text(83,y,c['title'],8)
                for x,n in zip((234,267,300),c['size_mm']):book.text(x,y,num(n),9)
                book.text(335,y,'未定义 / 实心外观占位',8,MUTED)
                y+=11
            book.end()
        book.save()
        summaries.append({'file':names[volume],'pages':book.page,'index':book.index})
    return summaries


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=ROOT/'tmp/pdfs/drawing-data.json')
    parser.add_argument('--output',type=Path,default=ROOT/'output/pdf')
    parser.add_argument('--font',type=Path,default=Path('/Users/miclle/Library/Fonts/AlibabaPuHuiTi-2-55-Regular.ttf'))
    args=parser.parse_args()
    result=make_books(json.loads(args.data.read_text()),args.output,args.font)
    print(json.dumps(result,ensure_ascii=False,indent=2))
