"""Candidate curved-arm kit overlay. Preserves the existing assembly unchanged.

Builds an explicitly unconfirmed envelope and reports interference, rather than
silently resizing speaker chambers to fit an unmeasured bought-in mechanism.
"""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
import FreeCAD as App
import Part
from hinges import moving_names, rotation as hinge_rotation, check_installation

ROOT = Path(__file__).resolve().parents[1]
V = App.Vector


def build_study():
    cfg = json.loads((ROOT / 'cad/selected-mechanism.json').read_text())
    base_path = ROOT / 'cad/lumi-three-driver.FCStd'
    output_path = ROOT / 'cad/lumi-selected-mechanism-fit.FCStd'
    # Reopening a saved file changes its document name; also match its real path.
    for opened in App.listDocuments().values():
        if (opened.Name == 'LumiMechanismStudy' or
                (opened.FileName and Path(opened.FileName).resolve() == output_path.resolve())):
            raise RuntimeError(f'Save manual edits separately and close {opened.Name} before rebuilding')
    with tempfile.TemporaryDirectory() as tmp:
        source_path = Path(tmp) / 'MechanismStudySource.FCStd'
        shutil.copy2(base_path, source_path)
        source = App.openDocument(str(source_path))
        try:
            base_parameters = json.loads(source.getObject('GeometryDatums').BuildParametersJSON)
            doc = App.newDocument('LumiMechanismStudy')
            doc.Label = '弯臂机芯装配核对 · 尺寸待确认'
            groups = {}
            for group_name in ['Cabinet', 'Front', 'Deck', 'Audio', 'Electronics', 'Cover', 'Feet']:
                group = doc.addObject('App::DocumentObjectGroup', group_name)
                group.Label = source.getObject(group_name).Label
                groups[group_name] = group
                for original in source.getObject(group_name).Group:
                    group.addObject(doc.copyObject(original, False))
            controls = doc.addObject('App::DocumentObjectGroup', 'Controls')
            controls.Label = '原外观旋钮占位（套装控制接口待确认）'
            for name in ['ControlBase', 'ControlKnob']:
                controls.addObject(doc.copyObject(source.getObject(name), False))
        finally:
            App.closeDocument(source.Name)
    kit = doc.addObject('App::DocumentObjectGroup', 'SelectedKit')
    kit.Label = '指定弯臂款 · 外观占位'
    analysis = doc.addObject('App::DocumentObjectGroup', 'FitAnalysis')
    analysis.Label = '安装包络与干涉 · 非实物零件'
    # Preserve inherited electronic spaces without claiming the kit needs a preamp.
    doc.getObject('Amplifier').Label = '功放板 · 含散热片整体包络（用户提供尺寸）'
    doc.getObject('PhonoBoard').Label = '备用电子预留区（不代表另需唱放）'
    doc.getObject('ConnectorPlate').Label = '套装 RCA 后板预留区（孔位待确认）'
    doc.getObject('FloatingDeck').Label = '现有承载板（机芯开口与孔位待调整）'

    def add(name, label, shape, color=(0.09, 0.095, 0.10), diagnostic=False):
        if shape.isNull() or not shape.isValid():
            raise ValueError('Invalid geometry: ' + name)
        obj = doc.addObject('Part::Feature', name)
        obj.Label, obj.Shape = label, shape
        obj.addProperty('App::PropertyBool', 'IsDiagnostic', 'Study').IsDiagnostic = diagnostic
        obj.addProperty('App::PropertyString', 'DimensionBasis', 'Study').DimensionBasis = cfg['assumption_note']
        (analysis if diagnostic else kit).addObject(obj)
        if App.GuiUp:
            obj.ViewObject.ShapeColor = color
            obj.ViewObject.DisplayMode = 'Flat Lines'
            obj.ViewObject.LineColor = (0.12, 0.12, 0.12)
            obj.ViewObject.Visibility = not diagnostic
        return obj

    h = base_parameters['cabinet_top']
    cx, cy, radius = cfg['platter_center_x'], cfg['platter_center_y'], cfg['platter_diameter'] / 2
    left, front = cx - radius, cy - cfg['nominal_depth'] / 2
    right = left + cfg['nominal_width']
    plate = Part.makeCylinder(radius, 2, V(cx, cy, h))
    wing = Part.makeBox(right - (cx + radius - 25), 80, 2, V(cx + radius - 25, cy + 45, h))
    add('KitBase', '一体机芯基座外观占位', plate.fuse(wing))
    platter_top = h + 2 + cfg['platter_thickness']
    add('KitPlatter', f"候选 Ø{cfg['platter_diameter']:g} 唱盘（弯臂尺寸待确认）", Part.makeCylinder(radius, cfg['platter_thickness'], V(cx, cy, h + 2)))
    rings = []
    for r in [radius * 0.3, radius * 0.54, radius * 0.72, radius - 4]:
        rings.append(Part.makeCylinder(r, 0.3, V(cx, cy, platter_top)).cut(Part.makeCylinder(r - 0.5, 0.3, V(cx, cy, platter_top))))
    add('KitMatRings', '唱盘表面环纹示意', Part.makeCompound(rings), (0.24, 0.25, 0.26))
    add('KitSpindle', '机芯主轴示意', Part.makeCylinder(3.5, 10, V(cx, cy, platter_top)), (0.72, 0.74, 0.76))
    pivot = V(right - 45, cy + 96, h + 35)
    add('KitArmSupport', '机芯自带唱臂支座示意', Part.makeBox(25, 33, 35, V(pivot.x - 12.5, pivot.y - 16.5, h)))
    curve = Part.BSplineCurve()
    curve.interpolate([pivot, V(pivot.x, cy + 46, h + 35), V(pivot.x + 3, cy - 12, h + 32),
                       V(pivot.x + 19, cy - 56, h + 28), V(pivot.x + 33, cy - 86, h + 27),
                       V(pivot.x + 21, cy - 106, h + 27)])
    wire = Part.Wire(curve.toShape())
    circle = Part.Wire(Part.makeCircle(3.2, pivot, curve.tangent(curve.FirstParameter)[0]))
    add('KitCurvedArm', '弯臂外观近似（停放姿态）', wire.makePipeShell([circle], True, False), (0.72, 0.74, 0.76))
    add('KitCounterweight', '后部配重外观示意', Part.makeCylinder(10, 16, V(pivot.x, pivot.y + 17, h + 35), V(0, 1, 0)))
    add('KitHeadshell', '唱头壳外观占位', Part.makeBox(18, 27, 6, V(pivot.x + 8, cy - 130, h + 21)))
    add('KitCartridge', '随套装唱头占位（型号待核实）', Part.makeBox(12, 19, 5, V(pivot.x + 11, cy - 129, h + 16)))
    add('KitArmRest', '停臂架外观示意', Part.makeCylinder(4, 27, V(pivot.x + 2, cy + 25, h)))

    underbody = Part.makeBox(cfg['nominal_width'], cfg['nominal_depth'], cfg['underbody_depth_assumption'],
                             V(left, front, h - cfg['underbody_depth_assumption']))
    envelope = add('UnderbodyReservation', f"机芯下探包络 · {cfg['underbody_depth_assumption']:g} mm 为假设", underbody, (1.0, 0.60, 0.15), True)
    if App.GuiUp:
        envelope.ViewObject.Transparency = 80
    obstacles = [o for group in groups.values() for o in group.Group]
    overlaps = []
    for obj in obstacles:
        if not underbody.BoundBox.intersect(obj.Shape.BoundBox):
            continue
        common = underbody.common(obj.Shape)
        if common.Volume > 1e-5:
            overlaps.append({'part': obj.Name, 'label': obj.Label, 'overlap_mm3': round(common.Volume, 3)})
            hit = add('Interference' + obj.Name, '包络重叠 · ' + obj.Label, common, (0.90, 0.16, 0.12), True)
            if App.GuiUp:
                hit.ViewObject.Transparency = 10
    hinge_checks, hinge_metrics = check_installation(doc, base_parameters)
    upper = Part.makeCompound([o.Shape for o in kit.Group])
    lid = doc.getObject('DustCover').Shape
    lid_overlap = lid.common(upper).Volume
    roof_top = doc.getObject('AcousticRoof').Shape.optimalBoundingBox(False).ZMax
    study = doc.addObject('App::FeaturePython', 'StudyBasis')
    study.addProperty('App::PropertyString', 'ConfigurationJSON').ConfigurationJSON = json.dumps(cfg, ensure_ascii=False, sort_keys=True)
    study.addProperty('App::PropertyString', 'BaseSHA256').BaseSHA256 = hashlib.sha256(base_path.read_bytes()).hexdigest()
    study.addProperty('App::PropertyString', 'Status').Status = 'PENDING_DIMENSIONS_AND_MOUNTING_REDESIGN'
    doc.recompute()
    physical = [o for o in doc.Objects if o.TypeId == 'Part::Feature' and not getattr(o, 'IsDiagnostic', False)]
    import Import
    step_path = ROOT / 'cad/lumi-selected-mechanism-fit.step'
    Import.export(physical, str(step_path))
    doc.saveAs(str(output_path))
    exported = Part.read(str(step_path))
    expected = Part.makeCompound([o.Shape for o in physical])
    report = {
        'revision': cfg['revision'], 'selected_option': cfg['selected_option'],
        'base_sha256': study.BaseSHA256, 'assumptions': cfg,
        'geometry_checks': {
            'all_shapes_valid': all(o.Shape.isValid() for o in physical),
            'step_valid': exported.isValid(),
            'step_solids_match': len(exported.Solids) == len(expected.Solids),
            **hinge_checks,
            'step_volume_matches': abs(exported.Volume - expected.Volume) / expected.Volume < 1e-7,
        },
        'hinges': hinge_metrics,
        'fit': {
            'installation_released': False,
            'dimensions_confirmed': False,
            'mounting_holes_confirmed': cfg['mounting_holes_confirmed'],
            'status': study.Status,
            'nominal_plan_mm': [cfg['nominal_width'], cfg['nominal_depth']],
            'underbody_depth_assumption_mm': cfg['underbody_depth_assumption'],
            'existing_roof_depth_below_mount_mm': h - roof_top,
            'additional_roof_clearance_needed_mm': max(0, cfg['underbody_depth_assumption'] - (h - roof_top)),
            'underbody_reservation_clear': not overlaps,
            'underbody_overlaps': overlaps,
            'illustrative_closed_cover_clear': lid_overlap < 1e-5,
            'illustrative_cover_clearance_mm': lid.distToShape(upper)[0],
        },
        'limitations': ['尺寸图属于直臂配图，弯臂款尺寸尚未确认', '下探体为保守矩形空间，不是真实机芯轮廓，重叠不代表实物必然碰撞',
                        '合页及盖总成对示意机芯做1度开盖抽样；真实机芯和自动回臂运动未验证', 'STEP 仅导出装配示意，包络及红色干涉体保留在 FCStd'],
    }
    (ROOT / 'cad/mechanism-fit-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return doc, cfg, report


def render_study(doc, cfg):
    import FreeCADGui as Gui
    view = Gui.activeDocument().activeView()
    view.stopAnimating()
    view.setAnimationEnabled(False)
    view.setCameraType('Orthographic')
    rotation = App.Rotation(V(1, 1, 0), V(-1, 1, 2), V(1, -1, 1), 'ZXY')
    def save(name):
        view.setCameraOrientation(rotation.Q)
        view.fitAll()
        Gui.updateGui()
        view.saveImage(str(ROOT / 'previews' / name), 1600, 1200, 'White')
    p=json.loads((ROOT/'cad/parameters.json').read_text())
    originals={name:doc.getObject(name).Placement for name in moving_names()}
    for name,original in originals.items():
        doc.getObject(name).Placement=hinge_rotation(p,p['cover_angle_open']).multiply(original)
    doc.recompute()
    save('selected-mechanism-open.png')
    for name,original in originals.items():doc.getObject(name).Placement=original
    for name in ['Cover', 'SelectedKit', 'Controls', 'Front', 'Deck']:
        for obj in doc.getObject(name).Group:
            obj.ViewObject.Visibility = False
    for obj in doc.getObject('Cabinet').Group:
        obj.ViewObject.Transparency = 75
    doc.getObject('AcousticRoof').ViewObject.Visibility = False
    doc.getObject('BearingPocket').ViewObject.Visibility = False
    for obj in doc.getObject('FitAnalysis').Group:
        obj.ViewObject.Visibility = obj.Name in ['UnderbodyReservation', 'InterferenceAcousticRoof']
    save('selected-mechanism-clearance.png')
    doc.getObject('AcousticRoof').ViewObject.Visibility = True
    doc.getObject('BearingPocket').ViewObject.Visibility = True
    for obj in doc.getObject('FitAnalysis').Group:
        obj.ViewObject.Visibility = False
    for obj in doc.getObject('Cabinet').Group:
        obj.ViewObject.Transparency = 0
    for name in ['Cover', 'SelectedKit', 'Controls', 'Front', 'Deck']:
        for obj in doc.getObject(name).Group:
            obj.ViewObject.Visibility = True
    doc.recompute()
    view.fitAll()
    doc.save()


if __name__ == '__main__':
    doc, cfg, report = build_study()
    if App.GuiUp:
        render_study(doc, cfg)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not all(report['geometry_checks'].values()):
        raise RuntimeError('Mechanism study geometry/export validation failed')
