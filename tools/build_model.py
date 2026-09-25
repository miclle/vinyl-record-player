"""Record player assembly reconstruction. Run build.FCMacro in FreeCAD to rebuild.

All distances are millimetres. JSON drives regeneration; native Part features
remain independent, editable solids, not a fully constrained manufacturing tree.
"""
import csv
import json
import math
from pathlib import Path

import FreeCAD as App
import Part
from ac_inlet import installation as inlet_installation
from feet import installation as feet_installation
from hinges import installation as hinge_installation, dimensions as hinge_dimensions
from fascia import dimensions as fascia_dimensions, installation as fascia_installation
from model_sections import assign_section, section_objects

ROOT = Path(__file__).resolve().parents[1]
V = App.Vector
WOOD = (0.37, 0.225, 0.13)
SLAT = (0.48, 0.32, 0.20)
BLACK = (0.065, 0.072, 0.079)
SILVER = (0.73, 0.75, 0.77)
GRAY = (0.23, 0.25, 0.27)


def build_structure():
    p = json.loads((ROOT / 'cad/parameters.json').read_text())
    if p['driver_count'] != 3 or len(p['fullrange']['center_x']) != 2:
        raise ValueError('This layout requires one woofer and two full-range satellites')
    W, D, H = p['width'], p['depth'], p['cabinet_top']
    t, z0 = p['wall'], p['foot_height']
    foot_parts = feet_installation(p)
    hinge_parts = hinge_installation(p)
    fascia_shape, fascia_cuts = fascia_installation(p)
    fd = fascia_dimensions(p)
    deck_side = p['deck_side_clearance']
    deck_front = fd['face_rear'] + p['deck_front_fascia_clearance']
    deck_rear = D - t - p['deck_rear_clearance']
    deck_left = t + deck_side
    deck_right = W - t - deck_side
    deck_width = deck_right - deck_left
    deck_depth = deck_rear - deck_front
    isolator_centers = [(44,100), (W-44,100), (W/2,295)]
    if min(deck_side, p['deck_front_fascia_clearance'], p['deck_rear_clearance']) <= 0:
        raise ValueError('Floating deck clearances must be positive')
    if deck_width <= 0 or deck_depth <= 0:
        raise ValueError('Floating deck clearances leave no usable panel')
    required_footprints = [('spindle hole', p['platter_x'], p['platter_y'], 10.2)]
    required_footprints.extend(
        (f'elastic support {i+1}', x, y, 8)
        for i,(x,y) in enumerate(isolator_centers))
    for name,x,y,radius in required_footprints:
        if not (deck_left <= x-radius and x+radius <= deck_right
                and deck_front <= y-radius and y+radius <= deck_rear):
            raise ValueError(f'Floating deck excludes {name}')
    a = math.radians(p['front_angle'])
    inward = V(0, math.sin(a), -math.cos(a))
    front_y = lambda z: 8 + (z - (z0+t)) / math.tan(a)
    output = ROOT / 'cad/record-player.FCStd'
    for opened in App.listDocuments().values():
        if (opened.Name == 'RecordPlayerAssembly' or
                (opened.FileName and Path(opened.FileName).resolve() == output.resolve())):
            raise RuntimeError(f'Save manual edits separately and close {opened.Name} before rebuilding')
    doc = App.newDocument('RecordPlayerAssembly')
    doc.Label = '黑胶唱片机整机 · 安装待确认'
    sections = {}
    for name, label in [('Cabinet','01 胡桃木外壳'), ('Front','02 倾斜格栅与灯光'),
                        ('Deck','03 浮动唱盘底板'), ('Mechanism','04 唱盘与唱臂包络'),
                        ('Audio','05 一低音两全频与独立音腔'), ('Electronics','06 电子空间占位'),
                        ('Cover','07 透明盖与铰链'), ('Feet','08 脚垫')]:
        sections[name] = []

    def add(name, label, shape, group, color, basis='估算 / 待选型', material='概念件', transparency=0):
        if shape.isNull() or not shape.isValid() or not shape.Solids:
            raise ValueError('Invalid solid: '+name)
        obj = doc.addObject('Part::Feature', name)
        obj.Label, obj.Shape = label, shape
        obj.addProperty('App::PropertyString','DimensionBasis','Design').DimensionBasis = basis
        obj.addProperty('App::PropertyString','MaterialNote','Design').MaterialNote = material
        assign_section(obj, group)
        sections[group].append(obj)
        if App.GuiUp:
            obj.ViewObject.ShapeColor = color
            obj.ViewObject.LineColor = (0.10,0.10,0.10)
            obj.ViewObject.DisplayMode = 'Flat Lines'
            obj.ViewObject.LineWidth = 1.0
            obj.ViewObject.Transparency = transparency
        return obj

    def box(name,label,x,y,z,dx,dy,dz,group,color,**kw):
        return add(name,label,Part.makeBox(dx,dy,dz,V(x,y,z)),group,color,**kw)

    def cyl(name,label,r,h,base,group,color,direction=V(0,0,1),**kw):
        return add(name,label,Part.makeCylinder(r,h,base,direction),group,color,**kw)

    def slope(zlo,zhi,offset,thick,x=t,width=None):
        width = W-2*t if width is None else width
        points = [V(x,front_y(zlo)+offset,zlo),V(x,front_y(zhi)+offset,zhi),
                  V(x,front_y(zhi)+offset+thick,zhi),V(x,front_y(zlo)+offset+thick,zlo)]
        return Part.Face(Part.makePolygon(points+[points[0]])).extrude(V(width,0,0))

    # Separable cabinet panels. The nominal overall depth excludes rear connectors.
    box('SideLeft','左侧木板',0,0,z0,t,D,H-z0,'Cabinet',WOOD,material='12 mm 木板 / 胡桃木表面')
    box('SideRight','右侧木板',W-t,0,z0,t,D,H-z0,'Cabinet',WOOD,material='12 mm 木板 / 胡桃木表面')
    woofer=p['woofer']; tweeter=p['fullrange']
    # The full-depth bottom includes the front edge; no separate lower rail.
    bottom=Part.makeBox(W-2*t,D,t,V(t,0,z0))
    bottom=bottom.cut(Part.makeCylinder(woofer['cutout_diameter']/2,t+2,V(woofer['center_x'],woofer['center_y'],z0-1)))
    for part in foot_parts:
        for cutter in part['cutouts']:
            bottom = bottom.cut(cutter)
    add('Bottom','底板 · 低音向下开孔',bottom,'Cabinet',BLACK,material='12 mm 木板；低音开孔待选型')
    port=p['bass_port']; ac=p['acoustic']
    px,pz=port['center_x'],port['center_z']
    pr=port['inner_diameter']/2; outer_r=pr+port['wall_thickness']
    back=Part.makeBox(W-2*t,t,H-z0-t,V(t,D-t,z0+t))
    back=back.cut(Part.makeCylinder(outer_r,t+2,V(px,D-t-1,pz),V(0,1,0)))
    back=back.cut(Part.makeCylinder(port['flange_diameter']/2,port['flange_thickness']+1,
                                  V(px,D-port['flange_thickness'],pz),V(0,1,0)))
    inlet_opening, inlet_bolts, inlet_shape, _ = inlet_installation(p)
    back = back.cut(inlet_opening)
    for bolt in inlet_bolts:
        back = back.cut(bolt)
    for part in hinge_parts:
        for cut in part['wood_cuts']:
            back = back.cut(cut)
    add('Back','后板 · 倒相管、AC 与铰链盲预孔',back,'Cabinet',WOOD)
    inlet = add('ACInlet','8 字 AC 插座 · 开关保险一体式安装包络',inlet_shape,'Electronics',BLACK,
                basis='用户提供 8-F5 商家图；横装开孔 48×28 R3、2×Ø4.5 孔距 40；外形及端子为保守包络',
                material='采购件占位；接线、绝缘、螺钉及适用板厚待实物确认，未放行通电')
    inlet.addProperty('App::PropertyBool','ElectricalReleased','Installation').ElectricalReleased=False
    inlet.addProperty('App::PropertyBool','InstallationReleased','Installation').InstallationReleased=False
    tube=Part.makeCylinder(outer_r,port['length']-port['flange_thickness'],V(px,D-port['length'],pz),V(0,1,0))
    tube=tube.fuse(Part.makeCylinder(port['flange_diameter']/2,port['flange_thickness'],
                                   V(px,D-port['flange_thickness'],pz),V(0,1,0)))
    tube=tube.cut(Part.makeCylinder(pr,port['length']+2,V(px,D-port['length']-1,pz),V(0,1,0)))
    add('BassPort',f"后置倒相管 · Ø{port['inner_diameter']:g} × {port['length']:g} 可换试验件",tube,'Audio',(0.22,0.48,0.62),
        basis='按可用空间设计的试验初值；非 SC-2103 原厂调谐，密封固定及端口圆角待细化')
    fs=p['fascia']
    fascia=add('Fascia','前沿银色 T 型铝饰条',fascia_shape,'Front',SILVER,
               basis='用户选定 30×30×5 商家图；按总外廓、等厚居中 T 截面解释，圆角及公差待实测',
               material=f"铝合金 T 型材 {fs['face_height']:g}×{fs['overall_depth']:g}×{fs['thickness']:g}；安装长 {fd['length']:g} mm")
    fascia.addProperty('App::PropertyBool','InstallationReleased','Installation').InstallationReleased=False
    # Thin cloth proxy; actual cloth is acoustically open, unlike this visual solid.
    cloth = add('GrilleCloth','透声布外观占位（非实心材料）',slope(z0+t,H-22,4,0.5),'Front',BLACK,material='透声织物（薄实体仅用于显示）')
    n=p['slat_count']
    for i in range(n):
        z=z0+t+2+i*p['slat_pitch']
        start=V(t,front_y(z),z)
        along=V(0,math.cos(a),math.sin(a))*p['slat_face_width']
        normal=inward*p['slat_thickness']
        points=[start,start+along,start+along+normal,start+normal]
        slat=Part.Face(Part.makePolygon(points+[points[0]])).extrude(V(W-2*t,0,0))
        add('Slat%02d'%(i+1),'横向木格栅 %02d'%(i+1),slat,'Front',SLAT,
            material=f"矩形木饰条 / 面宽 {p['slat_face_width']:g} / 法向厚 {p['slat_thickness']:g} mm")
    box('LightChannel','灯带铝槽占位',t+6,7,H-22,W-2*t-12,14,2,'Front',SILVER)
    box('LightDiffuser','3000 K 暖光扩散片',t+8,8,H-23,W-2*t-16,12,1,'Front',(1.0,0.64,0.22),material='扩散片 / 光色示意')

    # Two sealed trial satellite chambers and one central rear-ported chamber.
    zlo,zhi=z0+t,ac['roof_bottom_z']
    rear=ac['satellite_rear_y']; pt=ac['partition_thickness']
    left,right=p['acoustic_divider_x']
    baffle_y_thickness=ac['baffle_thickness']/math.sin(a)
    baffle=slope(zlo,zhi,8,baffle_y_thickness)
    speaker_centres=[]
    for x in tweeter['center_x']:
        centre=V(x,front_y(tweeter['center_z'])+8,tweeter['center_z'])
        speaker_centres.append(centre)
        baffle=baffle.cut(Part.makeCylinder(tweeter['cutout_diameter']/2,30,centre-inward*5,inward))
    add('Baffle','左右全频斜面障板',baffle,'Audio',BLACK,
        material=f"法向厚 {ac['baffle_thickness']:g} mm 障板；上下斜口修切，开孔待实测")
    roof=Part.makeBox(W-2*t,rear+pt,ac['roof_thickness'],V(t,0,zhi)).fuse(
        Part.makeBox(right+pt-left,D-t-rear-pt,ac['roof_thickness'],V(left,rear+pt,zhi)))
    # A sealed local recess clears the generic bearing without opening the low chamber.
    bx,by=p['platter_x'],p['platter_y']
    roof=roof.cut(Part.makeCylinder(14,ac['roof_thickness']+2,V(bx,by,zhi-1)))
    for cutter in fascia_cuts:
        roof=roof.cut(cutter)
    add('AcousticRoof','三音腔共用顶板 · 中部延伸至后板',roof,'Audio',GRAY)
    pocket_bottom=H-40
    pocket=Part.makeCylinder(14,zhi+ac['roof_thickness']-pocket_bottom,V(bx,by,pocket_bottom)).cut(
        Part.makeCylinder(12,zhi+ac['roof_thickness']-pocket_bottom-1,V(bx,by,pocket_bottom+2)))
    add('BearingPocket','通用轴承密封避让杯（当前机芯待重做）',pocket,'Audio',GRAY)
    rear_panels=Part.makeCompound([
        Part.makeBox(left-t,pt,zhi-zlo,V(t,rear,zlo)),
        Part.makeBox(W-t-right-pt,pt,zhi-zlo,V(right+pt,rear,zlo))])
    add('AcousticRear','左右全频腔后板 · 密封试装',rear_panels,'Audio',GRAY)
    for side,x in zip(['Left','Right'],p['acoustic_divider_x']):
        inner_offset=8+baffle_y_thickness
        pts=[V(x,front_y(zlo)+inner_offset,zlo),V(x,D-t,zlo),V(x,D-t,zhi),V(x,front_y(zhi)+inner_offset,zhi)]
        divider=Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(pt,0,0))
        add('AcousticDivider'+side,'低音腔'+('左' if side=='Left' else '右')+'全深隔板',divider,'Audio',GRAY)

    def driver(name,label,c,axis,spec,role):
        r=spec['cutout_diameter']/2
        flange_thickness=spec['flange_thickness']
        depth=spec['total_height']-flange_thickness
        if depth <= 0 or flange_thickness <= 0:
            raise ValueError('Driver total height must exceed positive flange thickness')
        magnet_r=r*0.6; magnet_h=min(14,depth*0.35); cone_h=depth*0.35
        flange=Part.makeCylinder(spec['flange_diameter']/2,flange_thickness,c-axis*flange_thickness,axis).cut(Part.makeCylinder(r-1,flange_thickness+1,c-axis*(flange_thickness+0.5),axis))
        cone=Part.makeCone(r-1,r*0.35,cone_h,c,axis).cut(Part.makeCone(r-2,r*0.35-1,cone_h,c-axis*0.7,axis))
        magnet=Part.makeCylinder(magnet_r,magnet_h,c+axis*(depth-magnet_h),axis)
        basket=Part.makeCone(r,magnet_r,depth-magnet_h,c,axis).cut(Part.makeCone(r-1,magnet_r-1,depth-magnet_h,c,axis))
        obj=add(name,label,Part.makeCompound([flange,cone,basket,magnet]),'Audio',BLACK,basis='用户提供口端外径与总高；开孔、边沿厚度及内部轮廓暂估')
        obj.addProperty('App::PropertyString','DriverRole','Installation').DriverRole=role
        obj.addProperty('App::PropertyVector','MountCentre','Installation').MountCentre=c
        obj.addProperty('App::PropertyVector','InwardAxis','Installation').InwardAxis=axis
        for key,value in [('FlangeDiameter',spec['flange_diameter']),('CutoutDiameter',spec['cutout_diameter']),('ReservedDepth',depth),('TotalHeight',spec['total_height']),('FlangeThickness',flange_thickness)]:
            obj.addProperty('App::PropertyLength',key,'Installation');setattr(obj,key,value)

    for side,c in zip(['Left','Right'],speaker_centres):
        driver('Tweeter'+side,('左' if side=='Left' else '右')+'全频 · SC-2103 安装占位',c,inward,tweeter,'fullrange')
    driver('Woofer','后排低音 · SC-2103 朝下安装占位',V(woofer['center_x'],woofer['center_y'],z0),V(0,0,1),woofer,'woofer')

    support=Part.makeCompound([Part.makeBox(left-t-8,30,8,V(t+8,280,H-22)),
                               Part.makeBox(W-t-8-right-pt,30,8,V(right+pt,280,H-22))])
    add('RearSupport','后部两侧隔振承托梁',support,'Deck',GRAY)
    for i,(x,y) in enumerate(isolator_centers):
        cyl('Isolator%d'%i,'弹性支承 %d（刚度待定）'%(i+1),8,8,V(x,y,H-14),'Deck',(0.12,0.15,0.16))
    # Clearances are installation assumptions, not verified suspension travel.
    deck_shape=Part.makeBox(deck_width,deck_depth,p['deck_thickness'],
                            V(deck_left,deck_front,H-p['deck_thickness']))
    deck_shape=deck_shape.cut(Part.makeCylinder(10.2,p['deck_thickness']+2,V(p['platter_x'],p['platter_y'],H-p['deck_thickness']-1)))
    deck=add('FloatingDeck','唱盘与唱臂共用浮动底板',deck_shape,'Deck',BLACK,material='结构底板 / 6 mm 占位；主轴孔 Ø20.4 待选型')
    amplifier=p['amplifier']
    if amplifier['rotation_degrees'] not in (0,90):
        raise ValueError('Amplifier rotation must be 0 or 90 degrees')
    amp_x,amp_y=(amplifier['width'],amplifier['length']) if amplifier['rotation_degrees']==90 else (amplifier['length'],amplifier['width'])
    box('Amplifier','功放板 · 含散热片整体包络',amplifier['x'],amplifier['y'],
        z0+t+amplifier['bottom_clearance_assumption'],
        amp_x,amp_y,amplifier['height'],
        'Electronics',(0.11,0.34,0.28),
        basis='用户提供含散热片外廓长宽高；离底板间距暂估，安装孔位未知',
        material='功放板及散热片整体占位；未细化散热片、端子和支柱')
    phono=p['phono_board']
    box('PhonoBoard','唱放板空间占位',*[phono[k] for k in ['x','y','z','length','width','height']],'Electronics',(0.12,0.32,0.28))
    transformer=p['power_transformer']
    length,width,height=(transformer[k] for k in ['body_length','body_width','body_height'])
    span=transformer['mount_span']; ear_thickness=transformer['mount_thickness_assumption']
    if not (0 < length <= span and width > 0 and 0 < ear_thickness < height):
        raise ValueError('Invalid transformer body or mounting envelope dimensions')
    tx,ty=transformer['center_x'],transformer['center_y']
    base_z=z0+t
    body=Part.makeBox(length,width,height,V(tx-length/2,ty-width/2,base_z))
    # Full-width, symmetric foot envelope; actual ear outline and holes are unknown.
    feet=Part.makeBox(span,width,ear_thickness,V(tx-span/2,ty-width/2,base_z))
    power=add('PowerTransformer','扬声器电源变压器 · 含固定耳包络',body.fuse(feet).removeSplitter(),
        'Electronics',(0.48,0.34,0.19),
        basis='本体长宽高与固定耳总长由用户提供；耳宽按本体宽保守预留，耳厚为参数中的暂估值，孔位未知',
        material='变压器空间占位；电气、散热与磁场影响未验证')
    for key,value in [('BodyLength',length),('BodyWidth',width),('BodyHeight',height),
                      ('MountSpan',span),('MountThicknessAssumption',ear_thickness)]:
        power.addProperty('App::PropertyLength',key,'Installation');setattr(power,key,value)

    box('ConnectorPlate','后部接口安装板占位',324,D-t-2,z0+39,105,2,32,'Electronics',BLACK)
    # Connector holes are intentionally deferred until actual parts are selected.

    cx,cy=p['platter_x'],p['platter_y']
    cyl('MotorEnvelope','马达空间占位',18,34,V(cx-76,cy+55,H-40),'Mechanism',GRAY)
    cyl('BearingEnvelope','主轴轴承空间占位',10,36,V(cx,cy,H-36),'Mechanism',SILVER)
    cyl('PlatterHub','唱盘支承轮毂',32,3,V(cx,cy,H),'Mechanism',BLACK)
    cyl('Platter',f"Ø{p['platter_diameter']:g} 唱盘",p['platter_diameter']/2,12,V(cx,cy,H+3),'Mechanism',BLACK,basis='直径初值来自官方；厚度估算',material='唱盘总成占位')
    cyl('PlatterMat','唱片垫',149,2,V(cx,cy,H+15),'Mechanism',(0.09,0.095,0.10))
    # Fine rim is geometry rather than a drawn circle.
    rim=Part.makeCylinder(143,0.12,V(cx,cy,H+17)).cut(Part.makeCylinder(142.7,0.12,V(cx,cy,H+17)))
    add('MatRing','唱片垫细环',rim,'Mechanism',SILVER)
    cyl('Spindle','主轴',3.5,11,V(cx,cy,H+17),'Mechanism',SILVER)
    cyl('ControlBase','左前旋钮底座',17,2,V(46,43,H),'Mechanism',GRAY)
    cyl('ControlKnob','多功能旋钮',16,14,V(46,43,H+2),'Mechanism',BLACK)
    theta=math.radians(p['pivot_bearing_degrees'])
    pivot=V(cx+p['pivot_distance']*math.cos(theta),cy+p['pivot_distance']*math.sin(theta),H+38)
    cyl('ArmBase','唱臂底座',23,7,V(pivot.x,pivot.y,H),'Mechanism',BLACK)
    cyl('ArmColumn','唱臂支柱',10,31,V(pivot.x,pivot.y,H+7),'Mechanism',GRAY)
    # Pivot/stylus planar geometry: outer groove reference at R140.
    R=140.0; L=p['arm_effective_length']; d=p['pivot_distance']
    along=(R*R-L*L+d*d)/(2*d)
    across=math.sqrt(R*R-along*along)
    stylus=V(cx+along*math.cos(theta)+across*math.sin(theta),cy+along*math.sin(theta)-across*math.cos(theta),H+17.3)
    forward=V(stylus.x-pivot.x,stylus.y-pivot.y,0); forward.normalize()
    head_dir=App.Rotation(V(0,0,1),p['headshell_offset']).multVec(forward)
    arm_end=V(stylus.x-head_dir.x*21,stylus.y-head_dir.y*21,H+30)
    tube_vector=arm_end-pivot
    cyl('TonearmTube','唱臂管外观包络',3.6,tube_vector.Length,pivot,'Mechanism',BLACK,tube_vector)
    cyl('CounterweightRod','平衡锤轴',3.5,36,pivot,'Mechanism',SILVER,-forward)
    cyl('Counterweight','平衡锤包络',12,19,pivot-forward*30,'Mechanism',BLACK,-forward)
    head=Part.makeBox(14,28,3,V(-7,-24,H+27))
    rot=App.Rotation(V(0,0,1),math.degrees(math.atan2(head_dir.y,head_dir.x))-90)
    head.Placement=App.Placement(V(stylus.x,stylus.y,0),rot)
    add('Headshell','唱头壳外观包络',head,'Mechanism',BLACK)
    cartridge=Part.makeBox(12,16,7,V(-6,-12,H+20))
    cartridge.Placement=App.Placement(V(stylus.x,stylus.y,0),rot)
    add('Cartridge','唱头占位（非安装图）',cartridge,'Mechanism',(0.72,0.73,0.70))
    cyl('Stylus','针尖几何基准',0.45,2.7,stylus,'Mechanism',SILVER)
    cyl('ArmRest','唱臂支架占位',4,26,V(pivot.x+10,pivot.y-69,H),'Mechanism',BLACK)

    # Closed cover is a five-sided hollow shell, not a solid box.
    cw=p['cover_wall']; cb=p['cover_bottom']; ch=p['closed_height']-cb
    cover=Part.makeBox(W-2*t,D-4,ch,V(t,2,cb)).cut(Part.makeBox(W-2*t-2*cw,D-4-2*cw,ch,V(t+cw,2+cw,cb-cw)))
    for part in hinge_parts:
        for cut in part['cover_cuts']:
            cover = cover.cut(cut)
    hs=p['hinges']; hd=hinge_dimensions(p)
    lid=add('DustCover','烟灰透明防尘盖',cover,'Cover',(0.34,0.37,0.39),material=f"{cw:g} mm 亚克力概念壳；4×Ø{hs['cover_hole_diameter_assumption']:g} 铰链孔为安装假设",transparency=76)
    for i,part in enumerate(hinge_parts):
        for prefix,key,label,material,color in [
                ('HingeBase','fixed','定位合页固定叶','锌合金；HFA5751-3434 简化外形',BLACK),
                ('HingePin','moving','定位合页活动叶及轴筒','锌合金；与固定叶合计 1 只采购合页',BLACK),
                ('HingeSpacer','spacer','合页上盖补偿垫片',f"{hd['spacer']:g} mm 铝垫片；安装假设",SILVER),
                ('HingeBacking','backing','亚克力内侧压板',f"{hs['backing_thickness_assumption']:g} mm 铝板；安装假设",SILVER)]:
            obj=add(f'{prefix}{i}',f'{label} {i+1}',part[key],'Cover',color,
                    basis='用户选定 HFA5751-3434；57×51、孔距34×34、4×Ø5.2；轴线、外廓细节与安装见 references/hinges',material=material)
            obj.addProperty('App::PropertyBool','InstallationReleased','Installation').InstallationReleased=False
    for i,part in enumerate(foot_parts):
        foot=add(f'Foot{i}',f'VE 橡胶脚垫与 M8 螺杆 {i+1}',part['foot'],'Feet',BLACK,
                 basis='用户商家图：橡胶 Ø30×20、M8 外露23；螺纹以光杆表示，金属顶片厚度未定义',
                 material='已购橡胶脚垫总成；硬度、压缩量及承载未验证')
        mount=add(f'FootMount{i}',f'M8 脚垫固定座 {i+1}',part['mount'],'Feet',GRAY,
                  basis='用户商家图：底盘 Ø37×2.5、圆柱 Ø12×14.5、3×Ø5.5；孔分布圆及板预孔为参数中的假设',
                  material='已购镀黑锌固定座；有效螺纹及紧固方案待实物确认')
        for obj in (foot,mount):
            obj.addProperty('App::PropertyBool','InstallationReleased','Installation').InstallationReleased=False
        if App.GuiUp:
            foot.ViewObject.DiffuseColor=[SILVER if face.CenterOfMass.z >= p['feet']['rubber_height'] else BLACK
                                         for face in foot.Shape.Faces]

    # Stock dimensions describe a rectangular blank in the board's own plane,
    # not its tilted XYZ envelope. Compound panel objects contain two blanks.
    stock_specs={
        'SideLeft':(V(1,0,0),t,'矩形板'), 'SideRight':(V(1,0,0),t,'矩形板'),
        'Bottom':(V(0,0,1),t,f"矩形板；低音通孔；4×Ø{p['feet']['panel_hole_diameter_assumption']:g} 脚座通孔、12×Ø{p['feet']['pilot_diameter_assumption']:g} 深{p['feet']['pilot_depth_assumption']:g} 底面盲预孔（安装假设）"),
        'Back':(V(0,1,0),t,f"矩形板；倒相孔及沉台；AC 横孔 {p['ac_inlet']['cutout_width']:g}×{p['ac_inlet']['cutout_height']:g} R{p['ac_inlet']['cutout_radius']:g}、上下 2×Ø{p['ac_inlet']['mount_hole_diameter']:g} 孔距 {p['ac_inlet']['mount_hole_pitch']:g}；4×Ø{p['hinges']['wood_pilot_diameter_assumption']:g} 深{p['hinges']['wood_pilot_depth_assumption']:g} 后侧铰链盲预孔（假设）"),
        'Baffle':(inward,ac['baffle_thickness'],f'整数矩形备料；上下两边修 {90-p["front_angle"]:g}° 斜口至安装竖高 {zhi-zlo:g}；另开法向孔'),
        'AcousticRoof':(V(0,0,1),ac['roof_thickness'],f"T 形板；成形前缘 Y={fd['roof_front']:g}；顶面前缘台阶宽 {fd['rebate_rear']-fd['roof_front']:g}、深 {fd['rebate_depth']:g}、余厚 {fd['remaining_roof']:g}；Ø28 轴承孔"),
        'AcousticRear':(V(0,1,0),pt,'两块独立矩形板'),
        'AcousticDividerLeft':(V(1,0,0),pt,'整数矩形备料；前缘按精确斜线修切'),
        'AcousticDividerRight':(V(1,0,0),pt,'整数矩形备料；前缘按精确斜线修切'),
        'RearSupport':(V(0,0,1),8,'两块独立矩形梁'),
        'FloatingDeck':(V(0,0,1),p['deck_thickness'],
                        f"矩形板；饰条后 {p['deck_front_fascia_clearance']:g}、左右各 {deck_side:g}、后板前 {p['deck_rear_clearance']:g} mm 名义间隙；另开主轴孔，机芯安装接口待定"),
    }
    for i in range(n):
        stock_specs[f'Slat{i+1:02}']=(inward,p['slat_thickness'],'矩形截面成品条；整体倾斜安装，无需把截面切成斜四边形')
    stock_rows=[]
    for name,(normal,thickness,note) in stock_specs.items():
        obj=doc.getObject(name)
        sizes=[]
        for solid in obj.Shape.Solids:
            aligned=solid.copy()
            aligned.Placement=App.Placement(V(),App.Rotation(normal,V(0,0,1))).multiply(aligned.Placement)
            bb=aligned.optimalBoundingBox(False)
            sizes.append(sorted([bb.XLength,bb.YLength],reverse=True))
        length=math.ceil(max(size[0] for size in sizes)-1e-6)
        width=math.ceil(max(size[1] for size in sizes)-1e-6)
        for prop,value in [('StockLength',length),('StockWidth',width),('StockThickness',thickness)]:
            obj.addProperty('App::PropertyLength',prop,'Woodworking');setattr(obj,prop,value)
        obj.addProperty('App::PropertyVector','StockNormal','Woodworking').StockNormal=normal
        obj.addProperty('App::PropertyInteger','StockCount','Woodworking').StockCount=len(sizes)
        obj.addProperty('App::PropertyString','StockNote','Woodworking').StockNote=note
        stock_rows.append([name,obj.Label,len(sizes),length,width,thickness,note])
    with (ROOT/'cad/wood-cut-list.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f,lineterminator='\n')
        writer.writerow(['ID','板件','数量','备料长_mm','备料宽_mm','名义板厚_mm','后续加工说明'])
        writer.writerows(stock_rows)

    info=doc.addObject('App::FeaturePython','GeometryDatums')
    info.Label='尺寸基准（JSON 修改后重建）'
    info.addProperty('App::PropertyString','BuildParametersJSON','Build').BuildParametersJSON=json.dumps(p,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    info.setEditorMode('BuildParametersJSON',1)
    for name,value in [('Width',W),('Depth',D),('ClosedHeight',p['closed_height']),('PivotDistance',d),('EffectiveArmLength',L)]:
        info.addProperty('App::PropertyLength',name,'Dimensions');setattr(info,name,value)
        info.setEditorMode(name,1)
    info.addProperty('App::PropertyVector','SpindlePoint','Geometry').SpindlePoint=V(cx,cy,H+17.3)
    info.addProperty('App::PropertyVector','PivotPoint','Geometry').PivotPoint=V(pivot.x,pivot.y,H+17.3)
    info.addProperty('App::PropertyVector','StylusPoint','Geometry').StylusPoint=stylus
    info.addProperty('App::PropertyVector','CoverHinge','Geometry').CoverHinge=hinge_dimensions(p)['axis']
    doc.recompute()
    return doc,p,sections


def build():
    from mechanism_study import add_study
    cfg = json.loads((ROOT / 'cad/mechanism.json').read_text())
    doc,p,sections = build_structure()
    try:
        report = add_study(doc,p,cfg)
        for name in [*sections, 'SelectedKit', 'Controls', 'FitAnalysis']:
            sections[name] = section_objects(doc, name)
        return doc,p,sections,report
    except Exception:
        App.closeDocument(doc.Name)
        raise


def deliver():
    from mechanism_study import save_report
    from assembly_pose import initialize, set_cover_angle
    doc,p,sections,report=build()
    initialize(doc)
    solids=[o for o in doc.Objects if o.TypeId=='Part::Feature' and o.Shape.Solids
            and not getattr(o,'IsDiagnostic',False) and not getattr(o,'IsReference',False)]
    import Import
    step_path=ROOT/'cad/record-player.step'
    Import.export(solids,str(step_path))
    exported=Part.read(str(step_path))
    expected=Part.makeCompound([o.Shape for o in solids])
    report['geometry_checks'].update(
        all_shapes_valid=all(o.Shape.isValid() for o in solids),
        step_valid=exported.isValid(),
        step_solids_match=len(exported.Solids)==len(expected.Solids),
        step_volume_matches=abs(exported.Volume-expected.Volume)/expected.Volume<1e-7)
    if App.GuiUp:
        import FreeCADGui as Gui
        Gui.activeDocument().activeView().viewAxonometric()
        Gui.activeDocument().activeView().fitAll()
    doc.recompute()
    set_cover_angle(doc,p,p['cover_angle_open'])
    if App.GuiUp:
        Gui.activeDocument().activeView().fitAll()
    doc.saveAs(str(ROOT/'cad/record-player.FCStd'))
    # Downstream renderers and callers work in the closed engineering datum.
    set_cover_angle(doc,p,0)
    save_report(report,ROOT)
    with (ROOT/'cad/parts.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f,lineterminator='\n')
        writer.writerow(['ID','零件','分组','材料说明','尺寸依据','包络X_mm','包络Y_mm','包络Z_mm'])
        for obj in solids:
            b=obj.Shape.optimalBoundingBox(False)
            section=obj.AssemblySection
            writer.writerow([obj.Name,obj.Label,section,getattr(obj,'MaterialNote','机芯概念占位'),
                             getattr(obj,'DimensionBasis','尺寸待确认'),
                             round(b.XLength,3),round(b.YLength,3),round(b.ZLength,3)])
    if not all(report['geometry_checks'].values()):
        raise RuntimeError('Mechanism geometry/export validation failed')
    return doc,p,sections


if __name__=='__main__':
    deliver()
