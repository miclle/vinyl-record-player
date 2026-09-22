"""Read-only CAD views and catalog for the two-page assembly guide.

Run assembly-guide.FCMacro in FreeCAD for renders; compose the PDF separately
with assembly_guide_pdf.py. All exploded placements exist only in a temporary
document, never in either saved manufacturing/fit-study source.
"""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import FreeCAD as App
import Part
import drawing_data

ROOT = Path(__file__).resolve().parents[1]
V = App.Vector

# Each physical object belongs to exactly one numbered entry. A bought-in
# assembly may combine several modeled objects; quantities below are explicit.
CATALOG = [
    ('W01', 1, '左右侧板', ['SideLeft', 'SideRight'], '2 块', '胡桃木饰面；基材待定'),
    ('W02', 1, '横向木格栅', [f'Slat{i:02}' for i in range(1, 9)], '8 条', '木饰条；木种待定'),
    ('F01', 1, '前沿银色 T 型铝饰条', ['Fascia'], '1 件', '铝合金 T 型材；固定待实测'),
    ('C01', 1, '透明防尘盖', ['DustCover'], '1 件', '烟灰亚克力；壁厚为暂估'),
    ('C02', 1, '铰链座与铰链轴', ['HingeBase0', 'HingeBase1', 'HingePin0', 'HingePin1'], '2 座 + 2 轴', '材质与固定方式待定'),
    ('C03', 1, '脚垫与固定座', [f'Foot{i}' for i in range(4)]+[f'FootMount{i}' for i in range(4)], '4 套', '已购橡胶脚垫与镀黑锌座；安装孔距暂估'),
    ('K01', 1, '一体机芯基座', ['KitBase'], '1 件', '采购机芯外观占位；材质待确认'),
    ('K02', 1, '唱盘与表面环纹', ['KitPlatter', 'KitMatRings'], '1 盘 + 4 道环纹', '环纹是外观示意，不代表独立唱片垫'),
    ('K03', 1, '机芯主轴', ['KitSpindle'], '1 件', '外观占位；材质与接口待确认'),
    ('K04', 1, '唱臂支座', ['KitArmSupport'], '1 件', '采购机芯自带；外观占位'),
    ('K05', 1, '弯曲唱臂', ['KitCurvedArm'], '1 件', '实心扫掠占位；真实管壁与材质未知'),
    ('K06', 1, '唱臂配重', ['KitCounterweight'], '1 件', '外观包络；质量与材质待确认'),
    ('K07', 1, '唱头壳与唱头', ['KitHeadshell', 'KitCartridge'], '各 1 件', '外观占位；唱头型号待确认'),
    ('K08', 1, '停臂架', ['KitArmRest'], '1 件', '外观占位；材质与固定方式待确认'),
    ('E01', 1, '控制旋钮与底座', ['ControlKnob', 'ControlBase'], '各 1 件', '实心外观占位；控制接口待确认'),
    ('W03', 2, '底板', ['Bottom'], '1 块', '木质板材；基材待定'),
    ('W04', 2, '后板', ['Back'], '1 块', '木质板材；基材待定'),
    ('W06', 2, '倾斜扬声器障板', ['Baffle'], '1 块', '木质板材；斜口按精确轮廓修切'),
    ('W07', 2, '三音腔共用顶板', ['AcousticRoof'], '1 块', '木质板材；基材待定'),
    ('W08', 2, '左右全频腔后板', ['AcousticRear'], '2 块', '一个 CAD 对象内的两块独立木板'),
    ('W09', 2, '低音腔全深隔板', ['AcousticDividerLeft', 'AcousticDividerRight'], '2 块', '木质板材；前缘按斜线修切'),
    ('W10', 2, '后部承托梁', ['RearSupport'], '2 件', '一个 CAD 对象内的两块独立木梁'),
    ('W11', 2, '浮动承载台面', ['FloatingDeck'], '1 块', '木质结构板；机芯开口仍待设计'),
    ('F02', 2, '透声布', ['GrilleCloth'], '1 片', '织物；CAD 薄实体仅用于显示'),
    ('F03', 2, '灯槽与扩散片', ['LightChannel', 'LightDiffuser'], '各 1 件', '灯槽／扩散片占位；LED 灯带未建模'),
    ('S01', 2, '轴承密封避让杯', ['BearingPocket'], '1 件', '材质待定；通用轴承遗留结构，待适配'),
    ('S02', 2, '台面弹性支承', [f'Isolator{i}' for i in range(3)], '3 件', '弹性材料；刚度待定'),
    ('A01', 2, '左右全频扬声器', ['TweeterLeft', 'TweeterRight'], '2 只', 'SC-2103 拆机件；安装孔暂估'),
    ('A02', 2, '底部朝下的低音单元', ['Woofer'], '1 只', 'SC-2103 拆机件；安装孔暂估'),
    ('A03', 2, '后置可换倒相管', ['BassPort'], '1 件', '材质待定；当前管长为试验初值'),
    ('E02', 2, '功放板与散热片', ['Amplifier'], '1 总成', '采购电子模块；尺寸已包含散热片'),
    ('E03', 2, '电源变压器', ['PowerTransformer'], '1 总成', '用户提供外廓；固定耳与孔位待确认'),
    ('E04', 2, '备用电子预留区', ['PhonoBoard'], '1 预留区', '空间占位，不代表必须另购唱放'),
    ('E05', 2, '后部接口板预留', ['ConnectorPlate'], '1 预留区', '接口板占位；真实孔位与材质待定'),
    ('E06', 2, 'AC 插座／开关／保险', ['ACInlet'], '1 总成', '8-F5 横装候选；外形与端子保守占位'),
]


def catalog_from_drawings(data):
    """Use the stable drawing references assigned by the CAD exporter."""
    references = {}
    cards_by_id = {}
    for volume in (1, 2, 3):
        cards = [c for c in data['cards'] if c['volume'] == volume]
        for card in cards:
            ref = card['drawing_code']
            for name in card['ids']:
                references.setdefault(name, set()).add(ref)
                cards_by_id[name] = card
    entries = []
    for code, page, title, names, quantity, material in CATALOG:
        if code == 'W02':
            names = cards_by_id['Slat01']['ids']
            quantity = f'{len(names)} 条'
        if code == 'C01':
            material = f'烟灰亚克力；壁厚 {cards_by_id["DustCover"]["thickness_mm"]:g} mm 暂估'
        if code == 'F01':
            card=cards_by_id['Fascia']
            material=f"铝合金 T 型材 {card['size_mm'][2]:g}×{card['size_mm'][1]:g}×{card['thickness_mm']:g}；固定待实测"
        entry = dict(code=code, page=page, title=title, ids=names,
                     quantity=quantity, material=material)
        entry['drawings'] = sorted({r for n in names for r in references[n]})
        entry['size_mm'] = cards_by_id[names[0]]['size_mm']
        if 'stock_mm' in cards_by_id[names[0]]:
            entry['stock_mm'] = cards_by_id[names[0]]['stock_mm']
        entries.append(entry)
    return entries


def overview_targets(entries):
    """Choose callout targets from the current assembly catalog."""
    overview = {e['code']: (e['ids'][0], (0.5, 0.5, 1)) for e in entries if e['page'] == 1}
    slats = next(e['ids'] for e in entries if e['code'] == 'W02')
    overview.update({'W01': ('SideRight', (1, 0.3, 0.5)),
                     'W02': (slats[(len(slats)-1)//2], (0.22, 0.0, 0.6)),
                     'C01': ('DustCover', (0.35, 0.5, 0.65)),
                     'C02': ('HingeBase1', (0.5, 0.5, 1)),
                     'C03': ('Foot1', (1, 0, 0)),
                     'K01': ('KitBase', (0.93, 0.85, 1)),
                     'K02': ('KitPlatter', (0.33, 0.4, 1)),
                     'K04': ('KitArmSupport', (0.1, 0, 0.4)),
                     'K05': ('KitCurvedArm', (0.75, 0.25, 0.6))})
    return overview


def check_coverage(doc, entries):
    physical = {o.Name for o in doc.Objects if o.TypeId == 'Part::Feature'
                and not getattr(o, 'IsDiagnostic', False)}
    listed = [n for e in entries for n in e['ids']]
    if len(listed) != len(set(listed)) or set(listed) != physical:
        raise ValueError(f'Guide coverage mismatch: missing={physical-set(listed)}, '
                         f'extra={set(listed)-physical}, duplicate={len(listed)!=len(set(listed))}')
    return len(physical)


def render(root=ROOT):
    import FreeCADGui as Gui
    from pivy import coin

    root = Path(root)
    out = root / 'tmp/assembly-guide'
    out.mkdir(parents=True, exist_ok=True)
    data = drawing_data.collect(root, project=False)
    entries = catalog_from_drawings(data)
    manifest = {'revision': data['revision'], 'sources': data['sources'],
                'entries': entries, 'views': {}, 'units': 'mm',
                'configuration': 'selected-curved-arm',
                'unmodeled': ['电源线与外接插头', '内部线束、端子护套', 'LED 灯带本体',
                              '紧固件、胶粘剂、密封件、吸音材料'],
                'nominal_cabinet_mm': [data['parameters'][k] for k in ('width', 'depth', 'closed_height')]}
    source = root / 'cad/lumi-selected-mechanism-fit.FCStd'
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / 'GuideReadOnly.FCStd'
        shutil.copy2(source, copy)
        doc = App.openDocument(str(copy))
        try:
            manifest['physical_object_count'] = check_coverage(doc, entries)
            physical = [o for o in doc.Objects if o.TypeId == 'Part::Feature'
                        and not getattr(o, 'IsDiagnostic', False)]
            originals = {o.Name: o.Placement for o in physical}
            codes = {n: e['code'] for e in entries for n in e['ids']}
            palette = {'W': (0.63, 0.43, 0.26), 'F': (0.62, 0.67, 0.70),
                       'C': (0.64, 0.73, 0.77), 'K': (0.30, 0.39, 0.46),
                       'S': (0.66, 0.54, 0.72), 'A': (0.29, 0.53, 0.65),
                       'E': (0.28, 0.60, 0.49)}
            view = Gui.activeDocument().activeView()
            view.stopAnimating()
            view.setAnimationEnabled(False)
            view.setCameraType('Orthographic')
            rotation = App.Rotation(V(1, 1, 0), V(-1, 1, 2), V(1, -1, 1), 'ZXY')
            # An orthographic square viewport makes camera projection independent
            # of the GUI window's current aspect ratio and screenshot size.
            def reset():
                for o in doc.Objects:
                    if o.TypeId == 'Part::Feature':
                        o.ViewObject.Visibility = o in physical
                for o in physical:
                    o.Placement = originals[o.Name]
                    vo = o.ViewObject
                    vo.ShapeColor = palette[codes[o.Name][0]]
                    vo.LineColor = (0.16, 0.20, 0.22)
                    vo.DisplayMode = 'Flat Lines'
                    vo.LineWidth = 1.0
                    vo.Transparency = 0
                doc.DustCover.ViewObject.Transparency = 75

            def translate(name, xyz):
                obj = doc.getObject(name)
                placement = obj.Placement
                placement.Base = placement.Base + V(*xyz)
                obj.Placement = placement

            def anchor(name, fraction=(0.5, 0.5, 1)):
                shape = doc.getObject(name).Shape
                b = shape.optimalBoundingBox(False)
                target = V(b.XMin + b.XLength * fraction[0],
                           b.YMin + b.YLength * fraction[1],
                           b.ZMin + b.ZLength * fraction[2])
                return shape.distToShape(Part.Vertex(target))[1][0][0]

            def save(key, orientation, targets):
                doc.recompute()
                view.setCameraOrientation(orientation.Q)
                view.fitAll()
                Gui.updateGui()
                camera = view.getCameraOrientation()
                inverse = camera.inverted()
                # Frame using visible shape bounds in camera coordinates. Set
                # height explicitly; saveImage uses an adjusted viewport at the
                # requested aspect ratio, so render square and use aspect 1.
                points = []
                for o in physical:
                    if o.ViewObject.Visibility:
                        b = o.Shape.optimalBoundingBox(False)
                        points.extend(inverse.multVec(V(x, y, z))
                                      for x in (b.XMin, b.XMax)
                                      for y in (b.YMin, b.YMax)
                                      for z in (b.ZMin, b.ZMax))
                lo = [min(getattr(p, a) for p in points) for a in ('x', 'y', 'z')]
                hi = [max(getattr(p, a) for p in points) for a in ('x', 'y', 'z')]
                center = V((lo[0]+hi[0])/2, (lo[1]+hi[1])/2, hi[2]+1500)
                height = max(hi[0]-lo[0], hi[1]-lo[1]) * 1.12
                scene = view.getCameraNode()
                scene.position.setValue(tuple(camera.multVec(center)))
                scene.height.setValue(height)
                scene.aspectRatio.setValue(1.0)
                # LEAVE_ALONE prevents the GUI viewport from changing the square
                # projection used for both the render and annotation anchors.
                scene.viewportMapping.setValue(coin.SoCamera.LEAVE_ALONE)
                scene.nearDistance.setValue(1.0)
                scene.farDistance.setValue(10000.0)
                Gui.updateGui()
                image_path = out / f'{key}.png'
                view.saveImage(str(image_path), 2400, 2400, 'White')
                projected = {}
                occluded = {}
                for code, (name, fraction) in targets.items():
                    world_point = anchor(name, fraction)
                    toward_camera = camera.multVec(V(0, 0, 1))
                    ray = Part.makeLine(world_point+toward_camera*0.05,
                                        world_point+toward_camera*2000)
                    blockers = [o.Name for o in physical if o.Name != name
                                and o.ViewObject.Visibility and o.ViewObject.Transparency < 50
                                and ray.BoundBox.intersect(o.Shape.BoundBox)
                                and o.Shape.common(ray).Length > 0.01]
                    if blockers:
                        occluded[code] = blockers
                    point = inverse.multVec(world_point)
                    projected[code] = [(point.x-center.x)/height+0.5,
                                       0.5-(point.y-center.y)/height]
                manifest['views'][key] = {'image': str(image_path.relative_to(root)),
                                           'anchors': projected,
                                           'occluded_by': occluded,
                                           'content_box': [(lo[0]-center.x)/height+0.5,
                                                           0.5-(hi[1]-center.y)/height,
                                                           (hi[0]-center.x)/height+0.5,
                                                           0.5-(lo[1]-center.y)/height],
                                           'visible_ids': sorted(o.Name for o in physical if o.ViewObject.Visibility)}

            reset()
            b = doc.DustCover.Shape.optimalBoundingBox(False)
            doc.DustCover.Placement = App.Placement(V(), App.Rotation(V(1, 0, 0), -70), V(0, b.YMax-1, b.ZMin))
            overview = overview_targets(entries)
            save('overview', rotation, overview)

            reset()
            for e in entries:
                if e['page'] == 1:
                    for name in e['ids']:
                        doc.getObject(name).ViewObject.Visibility = False
            # Expose the original geometry by separating layers; no parts resized.
            offsets = {'FloatingDeck': (-300, -200, 350), 'AcousticRoof': (200, 240, 170),
                       'BearingPocket': (480, 120, 100), 'Back': (100, 100, -40),
                       'ACInlet': (100, 100, -40), 'ConnectorPlate': (100, 100, -40),
                       'Baffle': (0, -95, 20), 'TweeterLeft': (0, -95, 20),
                       'TweeterRight': (0, -95, 20), 'GrilleCloth': (0, -175, -45),
                       'LightChannel': (0, -110, 70),
                       'LightDiffuser': (0, -135, 50), 'RearSupport': (-230, 200, 140),
                       'Isolator0': (-300, -380, 295), 'Isolator1': (-300, -380, 295),
                       'Isolator2': (-300, -380, 295), 'AcousticRear': (-40, 20, 90),
                       'PowerTransformer': (-150, 0, 35), 'PhonoBoard': (-130, -15, 20),
                       'Amplifier': (110, 0, 15), 'Woofer': (0, 0, 65)}
            for name, offset in offsets.items():
                translate(name, offset)
            doc.GrilleCloth.ViewObject.Transparency = 65
            targets = {e['code']: (e['ids'][0], (0.5, 0.5, 1)) for e in entries if e['page'] == 2}
            targets.update({'W03': ('Bottom', (0.8, 0.2, 1)),
                            'W04': ('Back', (0.95, 0, 0.9)),
                            'W06': ('Baffle', (0.5, 0.5, 0.8)),
                            'W08': ('AcousticRear', (0.09, 0.5, 0.8)),
                            'W09': ('AcousticDividerLeft', (0.5, 0.65, 0.8)),
                            'W10': ('RearSupport', (0.09, 0.5, 1)),
                            'W11': ('FloatingDeck', (0.7, 0.25, 1)),
                            'A01': ('TweeterRight', (0.5, 0, 0.5)),
                            'A03': ('BassPort', (0.5, 0.95, 1)),
                            'F02': ('GrilleCloth', (0.45, 0.4, 0.5))})
            save('exploded', rotation, targets)

            reset()
            for o in physical:
                o.ViewObject.Visibility = o.Name in ('Back', 'ACInlet', 'ConnectorPlate', 'BassPort')
            doc.Back.ViewObject.Transparency = 75
            save('rear', App.Rotation(V(-1, 0, 0), V(0, 0, 1), V(0, 1, 0), 'ZXY'),
                 {k: (n, (0.5, 1, 0.5)) for k, n in [('W04', 'Back'), ('E06', 'ACInlet'), ('E05', 'ConnectorPlate'), ('A03', 'BassPort')]})
        finally:
            App.closeDocument(doc.Name)
    for name, digest in manifest['sources'].items():
        if hashlib.sha256((root/'cad'/name).read_bytes()).hexdigest() != digest:
            raise ValueError('CAD source changed during guide generation: ' + name)
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest
