"""Read saved FreeCAD solids and export auditable orthographic drawing data.

Run with FreeCAD's Python. Does not rebuild or save either source document.
"""
import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path

import FreeCAD as App
import Part
import TechDraw

ROOT = Path(__file__).resolve().parents[1]
V = App.Vector


def bounds(shape):
    b = shape.optimalBoundingBox(False)
    return [round(v, 6) for v in (b.XLength, b.YLength, b.ZLength)], [round(v, 6) for v in (b.XMin, b.YMin, b.ZMin)]


def project_shape(shape, view):
    # Right-handed rotations: projected horizontal / vertical axes are explicit.
    rotations = {
        'top': ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        'front': ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
        'right': ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
        'rear': ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
        'left': ((0, -1, 0), (0, 0, 1), (-1, 0, 0)),
        'bottom': ((1, 0, 0), (0, -1, 0), (0, 0, -1)),
    }
    m = App.Matrix()
    for row, values in enumerate(rotations[view], 1):
        for col, value in enumerate(values, 1):
            setattr(m, f'A{row}{col}', value)
    s = shape.copy()
    s.transformShape(m)
    b = s.optimalBoundingBox(False)
    s.translate(V(-b.XMin, -b.YMin, 0))
    # TechDraw returns true visible-edge projection, not a mesh or silhouette box.
    svg = TechDraw.projectToSVG(s, V(0, 0, 1))
    w, h = b.XLength, b.YLength
    return {'size_mm': [round(w, 6), round(h, 6)],
            'svg': f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><g transform="translate(0,{h})">{svg}</g></svg>'}


def collect(root=ROOT, project=True):
    root = Path(root)
    p = json.loads((root / 'cad/parameters.json').read_text())
    cfg = json.loads((root / 'cad/selected-mechanism.json').read_text())
    source_paths = [root / 'cad/lumi-three-driver.FCStd', root / 'cad/lumi-selected-mechanism-fit.FCStd']
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    docs = []
    try:
        # Copies avoid touching/reusing a user's open document, including unsaved edits.
        with tempfile.TemporaryDirectory() as tmp:
            for i, path in enumerate(source_paths):
                copy = Path(tmp) / f'DrawingReadOnly{i}.FCStd'
                copy.write_bytes(path.read_bytes())
                docs.append(App.openDocument(str(copy)))
            base, study = docs
            if json.loads(base.GeometryDatums.BuildParametersJSON) != p:
                raise ValueError('Baseline parameter snapshot differs; rebuild the model first')
            if study.StudyBasis.BaseSHA256 != hashes[source_paths[0].name]:
                raise ValueError('Mechanism study is stale; rebuild the study first')
            if json.loads(study.StudyBasis.ConfigurationJSON) != cfg:
                raise ValueError('Mechanism parameter snapshot differs; rebuild the study first')
            cards = []
            covered = {'baseline': set(), 'study': set()}
            def add(name, volume, thickness, notes=(), aliases=(), split=False, source='baseline', main=None):
                doc = base if source == 'baseline' else study
                obj = doc.getObject(name)
                if obj is None:
                    raise ValueError(f'Missing drawing object {name}')
                shapes = obj.Shape.Solids if split else [obj.Shape]
                names = [name, *aliases]
                covered[source].update(names)
                for i, shape in enumerate(shapes, 1):
                    dims, pos = bounds(shape)
                    # Largest projected face is used as the primary view.
                    primary = main or max(('top', 'front', 'right'), key=lambda v: {'top': dims[0]*dims[1], 'front': dims[0]*dims[2], 'right': dims[1]*dims[2]}[v])
                    key = f'{name}:{i}' if split else name
                    title = obj.Label + (f' / 独立板件 {i}' if split else '')
                    positions = {n: bounds(doc.getObject(n).Shape)[1] for n in names}
                    card = {'key': key, 'ids': names, 'title': title, 'volume': volume,
                            'source': source, 'size_mm': dims, 'origin_mm': pos,
                            'quantity': len(names), 'positions_mm': positions,
                            'thickness_mm': thickness, 'notes': list(notes),
                            'basis': getattr(obj, 'DimensionBasis', '选定弯臂机芯外观假设，尺寸待实测'),
                            'primary': primary, 'views': {}}
                    if project:
                        card['views'] = {v: project_shape(shape, v) for v in ('top', 'front', 'right')}
                    holes=[]
                    if name in ('Bottom','AcousticRoof','FloatingDeck'):
                        spec=p['woofer'] if name=='Bottom' else None
                        hx,hy=(spec['center_x'],spec['center_y']) if spec else (p['platter_x'],p['platter_y'])
                        diameter=spec['cutout_diameter'] if spec else (28 if name=='AcousticRoof' else 20.4)
                        holes.append({'u_mm':hx-pos[0],'v_mm':hy-pos[1],'label':f'Ø{diameter:g}'})
                    elif name=='Back':
                        holes.append({'u_mm':p['bass_port']['center_x']-pos[0],
                                      'v_mm':p['bass_port']['center_z']-pos[2],
                                      'label':f"Ø{p['bass_port']['inner_diameter']+2*p['bass_port']['wall_thickness']:g}"})
                        inlet=p['ac_inlet']
                        holes.append({'u_mm':inlet['center_x']-pos[0],
                                      'v_mm':inlet['center_z']-pos[2],
                                      'label':f"AC {inlet['cutout_width']:g}×{inlet['cutout_height']:g} R{inlet['cutout_radius']:g}"})
                        for sign in (-1,1):
                            holes.append({'u_mm':inlet['center_x']-pos[0],
                                          'v_mm':inlet['center_z']+sign*inlet['mount_hole_pitch']/2-pos[2],
                                          'label':f"Ø{inlet['mount_hole_diameter']:g}"})
                    elif name=='Baffle':
                        for hx in p['fullrange']['center_x']:
                            holes.append({'u_mm':hx-pos[0],'v_mm':p['fullrange']['center_z']-pos[2],
                                          'label':f"Ø{p['fullrange']['cutout_diameter']:g} 法向"})
                    card['holes']=holes
                    if hasattr(obj,'StockLength'):
                        card['stock_mm']=[float(getattr(obj,key)) for key in ('StockLength','StockWidth','StockThickness')]
                        card['stock_note']=obj.StockNote
                    cards.append(card)
            W,D,H,t = (p[k] for k in ('width','depth','cabinet_top','wall'))
            sin = math.sin(math.radians(p['front_angle']))
            zlo = p['foot_height'] + t
            def f(n): return f'{n:.3f}'.rstrip('0').rstrip('.')
            def hole(x,y): return f'孔中心局部坐标 ({f(x)}, {f(y)})；基准为该板左前下角。'
            add('SideLeft',1,t,['长边沿 Y，板高沿 Z；两侧板同形，数量 2。'],['SideRight'])
            add('Bottom',1,t,[f"通孔 Ø{f(p['woofer']['cutout_diameter'])}（暂定低音开孔）。",hole(p['woofer']['center_x']-t,p['woofer']['center_y'])])
            add('Back',1,t,[f"通孔 Ø{f(p['bass_port']['inner_diameter']+2*p['bass_port']['wall_thickness'])}；后侧沉台 Ø{f(p['bass_port']['flange_diameter'])}，深 {f(p['bass_port']['flange_thickness'])}。",f"孔中心：距左边 {f(p['bass_port']['center_x']-t)}，距下边 {f(p['bass_port']['center_z']-zlo)}。"])
            inlet=p['ac_inlet']
            cards[-1]['notes'] += [
                f"AC 横装：{f(inlet['cutout_width'])}×{f(inlet['cutout_height'])}，R{f(inlet['cutout_radius'])}；中心局部 X/Z=({f(inlet['center_x']-t)}, {f(inlet['center_z']-zlo)})。",
                f"2×Ø{f(inlet['mount_hole_diameter'])}，上下孔距 {f(inlet['mount_hole_pitch'])}；先实物试孔，螺钉长度与板厚适配未确认。"]
            add('ACInlet',3,None,[
                '8-F5 两芯 C8 + 开关 + 保险座；横装，外形和端子按保守包络表示。',
                f"法兰厚 {f(inlet['flange_thickness'])}；自前表面总深 {f(inlet['total_depth'])}；背后另留 {f(inlet['wire_clearance_assumption'])} 接线空间（暂估）。",
                '商家资料未验证；保护接地不可用，整机绝缘、额定负载、保险及接线待确认，未放行通电。'])
            add('Fascia',1,6,['厚度方向 Y；前沿饰条高 20。'])
            add('LowerRail',1,8,['厚度方向 Y；梁高取模型 Z 尺寸。'])
            add('GrilleCloth',1,0.5*sin,[f'Y 向显示厚度 0.5；法向显示厚度 {f(0.5*sin)}。','透声布仅是薄实体外观占位，实物布厚未知。',f'斜面实际高度 {f((p["acoustic"]["roof_bottom_z"]-zlo)/sin)}；后倾 {f(90-p["front_angle"])}°。'])
            add('Slat01',1,p['slat_thickness'],[f'矩形截面：面宽 {f(p["slat_face_width"])} × 法向厚 {f(p["slat_thickness"])}；整体后倾 {f(90-p["front_angle"])}°。',f'竖向节距 {f(p["slat_pitch"])}；前表面下缘首条 Z={f(zlo+2)}，共 {p["slat_count"]} 条。','尺寸表为倾斜安装包络；直接下料使用上方矩形备料尺寸。'],[f'Slat{i:02}' for i in range(2,p['slat_count']+1)])
            add('LightChannel',1,2,['模型为实心薄块；未建 U 形槽，不能作为型材截面图。'])
            add('LightDiffuser',1,1,['扩散片外廓占位。'])
            add('DustCover',1,p['cover_wall'],['五面空心罩，底面开口；厚度适用于顶面和四侧。','本图为成形外廓，不是热弯展开图；弯曲半径、拼接未定义。'])
            add('HingeBase0',1,None,['实心安装座占位；材料壁厚及安装孔未定义。'],['HingeBase1'])
            add('HingePin0',1,None,['实心轴 Ø6 × 22；轴线沿 X，壁厚不适用。'],['HingePin1'])
            add('Foot0',1,None,['总高 26；上圆柱 Ø30 × 19；下锥台高 7、底径 Ø22。','实心弹性脚垫占位，壁厚不适用。'],['Foot1','Foot2','Foot3'])
            ac=p['acoustic']
            add('Baffle',2,ac['baffle_thickness'],[f'后倾 {f(90-p["front_angle"])}°；法向板厚 {f(ac["baffle_thickness"])}；Y 向厚度 {f(ac["baffle_thickness"]/sin)}。',f'上下两边修 {f(90-p["front_angle"])}° 斜口至安装竖高 {f(ac["roof_bottom_z"]-zlo)}；前表面斜长 {f((ac["roof_bottom_z"]-zlo)/sin)}。',f'2 × Ø{f(p["fullrange"]["cutout_diameter"])} 法向孔；中心 X={" / ".join(f(x) for x in p["fullrange"]["center_x"])}，Z={f(p["fullrange"]["center_z"])}（整机坐标）。','正视孔为椭圆；固定螺孔未知。'])
            add('AcousticRoof',2,ac['roof_thickness'],[f'前横板进深 {f(ac["satellite_rear_y"]+ac["partition_thickness"])}；中央后伸部宽 {f(p["acoustic_divider_x"][1]+ac["partition_thickness"]-p["acoustic_divider_x"][0])}。',f'后伸部左缘 X={f(p["acoustic_divider_x"][0])}；后缘 Y={f(D-t)}。',f'轴承孔 Ø28；中心 X={f(p["platter_x"])}, Y={f(p["platter_y"])}（整机坐标）。'])
            add('AcousticRear',2,ac['partition_thickness'],['此对象包含左右两块独立后板，分别绘制。','两块均由原实体直接读取，不以跨空区总包络下料。'],split=True)
            front_bottom=16+ac['baffle_thickness']/sin
            add('AcousticDividerLeft',2,ac['partition_thickness'],[f'前缘倾斜 {f(90-p["front_angle"])}°；后缘 Y={f(D-t)}。',f'下前角 Y={f(front_bottom)}；上前角 Y={f(front_bottom+(ac["roof_bottom_z"]-zlo)/math.tan(math.radians(p["front_angle"])))}。','两块同形；板厚方向 X。整数备料后按斜前缘精确修切。'],['AcousticDividerRight'])
            add('BearingPocket',2,2,['外径 Ø28；内径 Ø24；底厚 2；杯顶开口。','仅适配基线通用轴承；选定机芯安装时须重新核对。'])
            add('BassPort',2,p['bass_port']['wall_thickness'],[f"通径 Ø{f(p['bass_port']['inner_diameter'])}；管壁 {f(p['bass_port']['wall_thickness'])}；总长 {f(p['bass_port']['length'])}（含法兰）。",f"法兰 Ø{f(p['bass_port']['flange_diameter'])} × {f(p['bass_port']['flange_thickness'])}；主体长 {f(p['bass_port']['length']-p['bass_port']['flange_thickness'])}。",'长度是当前试验初值，非已验证声学调谐。'])
            add('FloatingDeck',2,p['deck_thickness'],['主轴通孔 Ø20.4（暂定）；机芯固定孔与外轮廓开口未设计。',hole(p['platter_x']-t-4,p['platter_y']-8)])
            add('RearSupport',2,8,['对象由左右两块承托梁组成，逐块标注。'],split=True)
            add('Isolator0',2,None,['实心弹性支承 Ø16 × 8；刚度未定，壁厚不适用。'],['Isolator1','Isolator2'])
            for name,role,aliases in [('Woofer','woofer',[]),('TweeterLeft','fullrange',['TweeterRight'])]:
                q=p[role]
                add(name,3,None,[f"单元本体：口端 Ø{f(q['flange_diameter'])}；轴向总高 {f(q['total_height'])}（用户提供）。",f"法兰厚 {f(q['flange_thickness'])}；孔径 Ø{f(q['cutout_diameter'])}；入腔深 {f(q['total_height']-q['flange_thickness'])}（假设）。",'下表为装配姿态 XYZ 包络；盆架壁厚等内部结构未经确认。'],aliases)
            a=p['amplifier']
            add('Amplifier',3,None,[f"本体长宽高 {f(a['length'])} × {f(a['width'])} × {f(a['height'])}，已含散热片。",f"装配旋转 {f(a['rotation_degrees'])}°；离底板 {f(a['bottom_clearance_assumption'])}（假设）。",'PCB 厚度及固定孔未知；整体高度不能作为板厚。'])
            add('PhonoBoard',3,None,['电子预留包络，PCB 厚度与固定孔未知。','弯臂核对版为备用预留区，不代表必须另装唱放。'])
            q=p['power_transformer']
            add('PowerTransformer',3,None,[f"本体 {f(q['body_length'])} × {f(q['body_width'])} × {f(q['body_height'])}；含耳总长 {f(q['mount_span'])}（用户提供）。",f"固定耳厚 {f(q['mount_thickness_assumption'])}、耳宽 {f(q['body_width'])} 为假设；本体壁厚未知。",'固定孔未建模；本体及耳共用底面。'])
            add('ConnectorPlate',3,2,['接口安装板外廓，RCA 等孔位未确认。'])
            for name,note in [('ControlBase','Ø34 × 2，实心底座。'),('ControlKnob','Ø32 × 14，实心旋钮占位。')]:
                add(name,3,None,[note,'壁厚不适用；控制接口待选定套装确认。'])
            kitnotes={
                'KitBase':(2,['基座外观薄板厚 2；不是已确认的机芯底板。']),
                'KitPlatter':(cfg['platter_thickness'],['Ø280 与厚 10 来自直臂配图，仅作弯臂款占位。']),
                'KitMatRings':(0.3,['四道装饰环：径向宽 0.5，高 0.3；不是唱片垫实物厚度。']),
                'KitSpindle':(None,['实心主轴 Ø7 × 10；壁厚不适用。']),
                'KitArmSupport':(None,['实心支座外观占位，壁厚和连接方式未知。']),
                'KitCurvedArm':(None,['外径 Ø6.4；模型为实心扫掠占位，真实管壁厚未知。','下表为弯曲臂整体包络，非管材下料长度。']),
                'KitCounterweight':(None,['实心配重包络 Ø20 × 16；壁厚不适用。']),
                'KitHeadshell':(6,['长宽高为外观占位，未包含真实槽孔。']),
                'KitCartridge':(None,['唱头包络 12 × 19 × 5；实物规格与壁厚未知。']),
                'KitArmRest':(None,['实心支架包络 Ø8 × 27；壁厚不适用。']),
            }
            for name,(thickness,notes) in kitnotes.items():
                add(name,3,thickness,notes+['弯臂款尺寸均待实测，不能据此定安装孔。'],source='study')
            # Baseline generic mechanism is historical context, kept in a compact appendix.
            for obj in base.Mechanism.Group:
                if obj.Name not in covered['baseline']:
                    add(obj.Name,4,None,['基线通用机芯占位；选定机芯版不含此件。','壁厚未定义；此处只记录现存实体的 XYZ 包络。'])
            # Shared parts are represented by the baseline sheets; verify shape parity.
            for obj in study.Objects:
                if obj.TypeId != 'Part::Feature' or getattr(obj,'IsDiagnostic',False):
                    continue
                if obj.Name in covered['baseline']:
                    original=base.getObject(obj.Name)
                    if any(abs(x-y)>1e-5 for x,y in zip(bounds(obj.Shape)[0]+bounds(obj.Shape)[1],bounds(original.Shape)[0]+bounds(original.Shape)[1])) or abs(obj.Shape.Volume-original.Shape.Volume)>1e-4:
                        raise ValueError(f'Shared object changed in study: {obj.Name}')
                    covered['study'].add(obj.Name)
            coverage={}
            for key,doc in [('baseline',base),('study',study)]:
                names={o.Name for o in doc.Objects if o.TypeId=='Part::Feature' and not getattr(o,'IsDiagnostic',False)}
                coverage[key+'_count']=len(names)
                coverage[key+'_missing']=sorted(names-covered[key])
                if coverage[key+'_missing']:
                    raise ValueError(f'Undrawn physical objects: {coverage[key+"_missing"]}')
            assemblies=[]
            specs=[
                ('selected-closed','选定弯臂机芯版 / 闭盖六面图',study,['Cabinet','Front','Deck','SelectedKit','Controls','Cover','Feet'],('top','front','right','bottom','rear','left')),
                ('internal','内部布置 / 移除盖与台面',base,['Cabinet','Audio','Electronics'],('top','front','right')),
                ('selected-kit','选定弯臂机芯 / 外观与安装包络',study,['SelectedKit','Controls'],('top','front','right')),
                ('generic','基线通用机芯 / 历史对照',base,['Mechanism'],('top','front','right')),
            ]
            for key,title,doc,groups,views in specs:
                objects=[o for g in groups for o in doc.getObject(g).Group]
                if key=='internal':
                    objects=[o for o in objects if o.Name not in ['AcousticRoof','SideRight','SideLeft','Back','Baffle','AcousticRear']]
                # Bottom view of the full assembly includes the downward-facing woofer.
                if key=='selected-closed':
                    objects += [study.getObject('Woofer'),study.getObject('ACInlet')]
                shape=Part.makeCompound([o.Shape for o in objects])
                assemblies.append({'key':key,'title':title,'size_mm':bounds(shape)[0],
                                   'views':{v:project_shape(shape,v) for v in views} if project else {}})
            return {'units':'mm','revision':p['revision'],'study_revision':cfg['revision'],
                    'sources':hashes,'parameters':p,'mechanism':cfg,'coverage':coverage,
                    'cards':cards,'assemblies':assemblies}
    finally:
        for doc in docs:
            App.closeDocument(doc.Name)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'tmp/pdfs/drawing-data.json')
    args=parser.parse_args()
    result=collect()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result['coverage'],ensure_ascii=False))
    print(args.output)
