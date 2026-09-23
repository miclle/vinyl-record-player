"""A3 detail-page layout; geometry and hole coordinates come from saved CAD data."""
import math
from reportlab.lib.colors import HexColor

MM = 72/25.4
DIM = '#805536'
MUTED = '#64727B'
INK = '#1E2930'


def num(value):
    return f'{value:.3f}'.rstrip('0').rstrip('.')


def hole_sheet_page(book, sheet):
    book.start(sheet['title'], sheet['code'], '成形边为定位基准 / 孔轴心坐标 / 单位 mm')
    vw, vh = sheet['size_mm']
    scale = min(0.5, 213/vw, 180/vh)
    ox, oy = 32, 53 if sheet['view'] in ('bottom','top') else 72
    dw, dh = vw*scale, vh*scale
    bottom = sheet['view']=='bottom'
    book.text(18,39,('底面仰视' if bottom else '前表面法向视图' if sheet['view']=='baffle_face' else
                    '罩内向后看' if sheet['key']=='DustCover' else '箱内向后看' if sheet['view']=='front' else '俯视')+
              f'  1:{num(1/scale)}  /  板厚 {num(sheet["thickness_mm"])}',10)
    book.projection(sheet['projection'], ox, oy, scale)
    book.hdim(ox, oy-7, dw, f'{sheet["axes"][0]} {num(vw)}', oy)
    book.vdim(ox-9, oy, dh, f'{sheet["axes"][1]} {num(vh)}', ox)
    datum_y = oy if bottom else oy+dh
    book.text(ox-3,datum_y+(0 if bottom else 4),'O',9,DIM,'right')
    book.line(ox,datum_y,ox+14,datum_y,DIM,0.8)
    book.text(ox+15,datum_y+3,'+X',8,DIM)
    dy = 1 if bottom else -1
    book.line(ox,datum_y,ox,datum_y+dy*14,DIM,0.8)
    book.text(ox+2,datum_y+dy*10,'+'+sheet['axes'][1],8,DIM)

    for h in sheet['holes']:
        x=ox+h['u_mm']*scale
        y=oy+(h['v_mm'] if bottom else vh-h['v_mm'])*scale
        book.line(x-1.6,y,x+1.6,y,MUTED)
        book.line(x,y-1.6,x,y+1.6,MUTED)
        identifier=h['id']
        if h['id'].startswith('J'):
            dx,dy=(-7,-10) if h['id'].endswith('1') else (7,-10)
        elif h['kind']=='blind':
            dx,dy={1:(6,0),2:(-6,5),3:(-6,-7)}[int(identifier[-1])]
        elif identifier.startswith('F'):
            dx,dy=(5,5) if h['v_mm']<vh/2 else (5,-5)
        elif sheet['key']=='Back':
            dx,dy={'H1':(16,15),'H2':(22,-2),'H3':(19,7),'H4':(19,-7)}[identifier]
        else:
            dx,dy=12,-12
        book.line(x,y,x+dx,y+dy,DIM)
        label=identifier
        if h['kind']=='through' and not identifier.startswith('F'):
            label+=' Ø'+num(h['diameter_mm'])
        book.text(x+dx+(1 if dx>=0 else -1),y+dy+1,label,7.5,DIM,
                  'left' if dx>=0 else 'right')
        if h.get('recess'):
            book.c.saveState()
            book.c.setStrokeColor(HexColor(DIM));book.c.setDash(2,2)
            book.c.circle(x*MM,(297-y)*MM,h['recess']['diameter_mm']/2*scale*MM,stroke=1,fill=0)
            book.c.restoreState()

    # Locate sparse holes with explicit baseline dimensions as well as the table.
    if sheet['key']!='Bottom':
        us=sorted({h['u_mm'] for h in sheet['holes'] if not h['id'].startswith('J')})
        for i,u in enumerate(us):
            book.hdim(ox,oy+dh+12+i*8,u*scale,num(u),oy+dh)
        dimensioned_holes=sheet['holes'][:2] if sheet['key']=='Back' else sheet['holes']
        vs=sorted({h['v_mm'] for h in dimensioned_holes})
        for i,v in enumerate(vs):
            book.vdim(ox+dw+8+i*7,oy+(vh-v)*scale,v*scale,num(v),ox+dw)

    if sheet['key']=='Back':
        lower,upper=sheet['holes'][2:4]
        cy=oy+(vh-upper['v_mm'])*scale
        book.vdim(ox+lower['u_mm']*scale-20,cy,
                  (upper['v_mm']-lower['v_mm'])*scale,
                  num(upper['v_mm']-lower['v_mm']),ox+lower['u_mm']*scale)

    book.text(269,39,'孔表 / 从 O 量至孔轴心',11)
    for x,label in [(269,'编号'),(294,sheet['axes'][0]),(319,sheet['axes'][1]),(344,'孔形 / 尺寸')]:
        book.text(x,49,label,8,MUTED)
    y=58
    for h in sheet['holes']:
        book.line(267,y-5,403,y-5)
        book.text(269,y,h['id'],8.5)
        book.text(294,y,num(h['u_mm']),8.5)
        book.text(319,y,num(h['v_mm']),8.5)
        if h['kind']=='rounded_rectangle':
            spec=f'{num(h["width_mm"])}×{num(h["height_mm"])} R{num(h["radius_mm"])} 通'
        else:
            spec='Ø'+num(h['diameter_mm'])+(' 深'+num(h['depth_mm']) if h['kind']=='blind' else ' 通')
        book.text(344,y,spec,8.5,DIM)
        y+=8.5
    if any(h.get('recess') for h in sheet['holes']):
        h=next(h for h in sheet['holes'] if h.get('recess'))
        r=h['recess']
        book.paragraph(269,y+5,f'{h["id"]} 后侧同心沉台：Ø{num(r["diameter_mm"])}，深 {num(r["depth_mm"])}。',132,9,DIM)
    book.text(269,max(y+22,220),'通 = 贯通；深 = 从指定加工面量取。',8,MUTED)
    y=248
    for note in sheet['notes']:
        y=book.paragraph(18,y,note,384,9,INK,4.5)+2
    if y>282:
        raise ValueError(f'Hole sheet notes overflow: {sheet["key"]}')
    book.end()


def section_page(book, section, p):
    book.start('倾斜扬声器障板 / 前部局部装配剖视','A-03','保存实体临时剖切 / 源 CAD 不变')
    book.text(18,39,f'沿 X={num(section["x_mm"])} 剖切，从右侧看；+Y 向右（箱内），+Z 向上。比例 1:1。',10)
    book.text(18,47,f'显示前部 Y=0..{num(section["y_limit_mm"])}；右端为截断边，不是板件接缝。',9,MUTED)
    ox, base_y, scale = 98, 228, 1
    for part in section['parts']:
        yy,zz=part['origin_mm'];w,h=part['size_mm']
        px,py=ox+yy*scale,base_y-(zz+h)*scale
        book.projection(part['projection'],px,py,scale)
    by_key={part['key']:part for part in section['parts']}
    anchors=[('AcousticRoof','音腔顶板',231,84),('Baffle','倾斜扬声器障板',231,125),
             ('Bottom','底板',231,192),('GrilleCloth','透声布',21,121),
             (f'Slat{max(1,(p["slat_count"]+1)//2):02}','木格栅',21,162),
             ('Fascia','T 型铝饰条',21,73)]
    for key,label,tx,ty in anchors:
        part=by_key[key];u,v=part['origin_mm'];w,h=part['size_mm']
        ax,ay=ox+(u+w/2)*scale,base_y-(v+h/2)*scale
        end=tx-3 if tx>ox else tx+36
        book.line(ax,ay,end,ty-1,DIM)
        book.text(tx,ty,label,10,INK)
    baffle=by_key['Baffle'];u,v=baffle['origin_mm'];w,h=baffle['size_mm']
    book.vdim(207,base_y-v-h,h,f'安装竖高 {num(h)}',ox+u+w)
    angle=90-p['front_angle']
    y=143
    for note in [f'相对竖直后倾 {num(angle)}°',
                 f'法向板厚 {num(p["acoustic"]["baffle_thickness"])} mm',
                 '上下斜口与底板、顶板贴合',
                 '前表面孔位及孔径：第 02 册 B-H01',
                 '板件三视及备料：第 02 册 B-P01']:
        book.text(231,y,note,9,DIM if y<156 else INK);y+=8
    # A separate angle diagram avoids covering narrow grille sections.
    px,py=330,225
    book.text(px-3,py+6,'倾角示意',8,MUTED)
    book.c.saveState();book.c.setDash(2,2)
    book.line(px,py,px,py-41,MUTED)
    book.c.restoreState()
    book.line(px,py,px+41*math.sin(math.radians(angle)),py-41*math.cos(math.radians(angle)),DIM)
    radius=25
    points=[]
    for i in range(19):
        a=math.radians(angle*i/18)
        points.append((px+radius*math.sin(a),py-radius*math.cos(a)))
    for first,second in zip(points,points[1:]):book.line(*first,*second,DIM)
    book.text(px+4,py-29,f'{num(angle)}°',9,DIM)
    fs=p['fascia'];ac=p['acoustic']
    web_bottom=p['cabinet_top']-(fs['face_height']+fs['thickness'])/2
    recess=ac['roof_bottom_z']+ac['roof_thickness']-web_bottom+fs['fit_clearance_assumption']
    book.text(231,61,f"T 型材 {num(fs['face_height'])} × {num(fs['overall_depth'])} × {num(fs['thickness'])}，宽面朝前",9,DIM)
    book.text(231,68,f"顶板台阶深 {num(recess)}；余厚 {num(ac['roof_thickness']-recess)}",9,DIM)
    book.text(231,75,f"含 {num(fs['fit_clearance_assumption'])} 胶层/试装余量，固定孔未定",8,MUTED)
    y=249
    for note in [
        '本剖面取箱体中线，避开两侧扬声器孔；用于看清格栅、透声布、障板、底板和顶板的相对位置。',
        '木格栅和透声布位于障板前方；闭盖整机图中障板受遮挡，不能从侧板外轮廓判断其倾角。',
        'T 型铝条槽隙为安装假设；本页不放行加工，根部圆角避让、胶层、连接螺孔及紧固工艺待实测。',
    ]:y=book.paragraph(18,y,note,384,9,INK,4.8)+2
    book.end()
