"""Curved-arm geometry and diagnostics within the main assembly.

Uses partial measurements and explicitly assumed local envelopes. Reports fit
conflicts without cutting the cabinet from incomplete bought-in part dimensions.
"""
import hashlib
import json
import math
from pathlib import Path
import FreeCAD as App
import Part
from model_sections import assign_section, section_objects
from hinges import moving_names, rotation as hinge_rotation, check_installation, interference_volume

ROOT = Path(__file__).resolve().parents[1]
V = App.Vector


def measurement_datums(cfg, support_z, compression=None):
    """Keep support plane, spring seat and platform faces distinct."""
    compression = cfg['display_spring_compression'] if compression is None else compression
    lo, hi = cfg['spring_compression_range']
    if not 0 <= lo <= compression <= hi < cfg['spring_free_height']:
        raise ValueError('Invalid spring compression range or display state')
    if not math.isclose(cfg['total_height'], cfg['seat_to_motor_bottom'] +
                        cfg['platform_thickness'] + cfg['arm_support_height']):
        raise ValueError('Measured height chain must equal total_height')
    height = cfg['spring_free_height'] - compression
    seat = support_z + height
    cx, cy = cfg['platter_center_x'], cfg['platter_center_y']
    points = [[cx + cfg['spring_radius'] * math.sin(hour * math.pi / 6),
               cy + cfg['spring_radius'] * math.cos(hour * math.pi / 6)]
              for hour in cfg['spring_clock_hours']]
    return dict(support_z_mm=support_z, spring_height_mm=height,
                spring_compression_mm=compression, seat_z_mm=seat,
                platform_top_z_mm=seat + cfg['platform_thickness'],
                lowest_z_mm=seat - cfg['seat_to_motor_bottom'],
                highest_z_mm=seat + cfg['platform_thickness'] + cfg['arm_support_height'],
                motor_depth_below_support_mm=cfg['seat_to_motor_bottom'] - height,
                spring_centers_xy_mm=points)


def local_underbody(cfg, seat):
    """Illustrative local regions, NOT a complete or verified machining envelope."""
    a = cfg['appearance_assumptions']
    cx, cy = cfg['platter_center_x'], cfg['platter_center_y']
    mx, my = a['motor_offset']
    motor = Part.makeCylinder(a['motor_diameter']/2, cfg['seat_to_motor_bottom'],
                             V(cx+mx, cy+my, seat-cfg['seat_to_motor_bottom']))
    transmission = Part.makeCylinder(a['transmission_diameter']/2, a['transmission_depth'],
                                    V(cx, cy, seat-a['transmission_depth']))
    width, depth, height = a['return_size']
    rx, ry = a['return_offset']
    linkage = Part.makeBox(width, depth, height, V(cx+rx-width/2, cy+ry-depth/2, seat-height))
    return motor.fuse(transmission).fuse(linkage).removeSplitter()


def _placed(shape, origin, yaw_degrees):
    """Rotate a local +X/-Y detail about Z, then move it into the assembly."""
    shape.rotate(V(), V(0, 0, 1), yaw_degrees)
    shape.translate(origin)
    return shape


def headshell_shape(rear, yaw_degrees, cfg, arm_z):
    """Approximate the pictured slotted headshell, connector and finger lift."""
    length = cfg['headshell_length']
    width = cfg['headshell_width']
    thickness = cfg['headshell_thickness']
    if length < 24 or width < 12 or thickness <= 0:
        raise ValueError('Headshell appearance requires length >= 24, width >= 12 and thickness > 0')
    if not 0 <= cfg['arm_connector_overlap'] < cfg['arm_connector_length']:
        raise ValueError('Arm connector overlap must be shorter than its positive length')
    if cfg['arm_connector_diameter'] <= 0 or cfg['finger_lift_length'] <= 0:
        raise ValueError('Arm connector diameter and finger lift length must be positive')
    body_z = arm_z - cfg['arm_connector_diameter'] / 2
    chamfer_depth = min(6.0, length * 0.12)
    corner_inset = min(4.0, width * 0.18)
    outline = [V(-width/2, 0, 0), V(width/2, 0, 0),
               V(width/2, -length+chamfer_depth, 0),
               V(width/2-corner_inset, -length, 0),
               V(-width/2+corner_inset, -length, 0),
               V(-width/2, -length+chamfer_depth, 0)]
    body = Part.Face(Part.makePolygon(outline + [outline[0]])).extrude(V(0, 0, thickness))
    # The photograph shows two long mounting slots near the cartridge end.
    slot_width = min(4.0, width * 0.18)
    slot_length = min(16.0, length * 0.31)
    slot_front_margin = min(7.0, length * 0.26)
    for x in (-width/4, width/4):
        slot = Part.makeBox(slot_width, slot_length, thickness+2,
                            V(x-slot_width/2, -length+slot_front_margin, -1))
        body = body.cut(slot)
    # Three shallow round pads reproduce the visible headshell top pattern.
    pad_radius = min(3.3, width * 0.15)
    for ratio in (0.25, 0.46, 0.67):
        body = body.fuse(Part.makeCylinder(pad_radius, 0.8,
                                           V(0, -length*ratio, thickness)))
    body = _placed(body.removeSplitter(), V(rear.x, rear.y, body_z), yaw_degrees)
    yaw = math.radians(yaw_degrees)
    direction = V(math.sin(yaw), -math.cos(yaw), 0)
    connector_start = rear - direction * (cfg['arm_connector_length'] - cfg['arm_connector_overlap'])
    connector = Part.makeCylinder(cfg['arm_connector_diameter']/2,
                                  cfg['arm_connector_length'], connector_start, direction)
    # Start inside the shell wall so the lift remains one robust exported solid.
    side = V(math.cos(yaw), math.sin(yaw), 0)
    lift_root = rear + direction * (length*0.6) + side * (width/2-1)
    finger_lift = Part.makeCylinder(1.5, cfg['finger_lift_length'], lift_root, side)
    return body.fuse(connector).fuse(finger_lift).removeSplitter(), direction, body_z


def cartridge_shape(rear, yaw_degrees, body_z, cfg):
    """Place the cartridge under the front half of the pictured headshell."""
    local = Part.makeBox(12, 19, 5, V(-6, -cfg['headshell_length']+4, -5))
    return _placed(local, V(rear.x, rear.y, body_z), yaw_degrees)


def closed_cover_metrics(lid, shapes):
    """Measure exact clearance, pruning parts whose bounding boxes are farther.

    Intersecting boxes use zero as their lower bound, including containment;
    only separated boxes can provide a positive distance lower bound.
    """
    overlap = sum(interference_volume(lid, shape) for shape in shapes)
    if overlap > 1e-5:
        return overlap, 0.0
    best = float('inf')
    for shape in shapes:
        b = shape.BoundBox
        box = Part.makeBox(b.XLength, b.YLength, b.ZLength, V(b.XMin,b.YMin,b.ZMin))
        bound = 0 if lid.common(box).Volume > 1e-9 else lid.distToShape(box)[0]
        if bound < best:
            best = min(best, lid.distToShape(shape)[0])
    return overlap, best


def add_study(doc, base_parameters, cfg):
    """Add the measured mechanism study to the generated main assembly."""
    measurement_datums(cfg, 0)  # Reject inconsistent measurement chains before opening documents.
    obstacle_sections = ['Cabinet', 'Front', 'Deck', 'Audio', 'Electronics', 'Cover', 'Feet']
    for name in ['ControlBase', 'ControlKnob']:
        obj = doc.getObject(name)
        assign_section(obj, 'Controls')
    for obj in section_objects(doc, 'Mechanism'):
        obj.addProperty('App::PropertyBool', 'IsReference', 'Design').IsReference = True
        if App.GuiUp:
            obj.ViewObject.Visibility = False
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
        assign_section(obj, 'FitAnalysis' if diagnostic else 'SelectedKit')
        if App.GuiUp:
            obj.ViewObject.ShapeColor = color
            obj.ViewObject.DisplayMode = 'Flat Lines'
            obj.ViewObject.LineColor = (0.12, 0.12, 0.12)
            obj.ViewObject.Visibility = not diagnostic
        return obj

    h = base_parameters['cabinet_top']
    datums = measurement_datums(cfg, h)
    a = cfg['appearance_assumptions']
    seat, platform_top = datums['seat_z_mm'], datums['platform_top_z_mm']
    cx, cy, radius = cfg['platter_center_x'], cfg['platter_center_y'], cfg['platter_diameter'] / 2
    right = cx - radius + cfg['nominal_width']
    plate = Part.makeCylinder(radius, a['base_disc_thickness'], V(cx, cy, seat))
    wing = Part.makeBox(cfg['platform_width'], cfg['platform_length'], cfg['platform_thickness'],
                       V(right-cfg['platform_width'], cy+a['platform_rear_offset']-cfg['platform_length'], seat))
    # Hollow sleeves depict spring outside space only; wire/rate are unmeasured.
    springs = []
    sr = a['spring_outer_diameter']/2
    for sx, sy in datums['spring_centers_xy_mm']:
        outer = Part.makeCylinder(sr, datums['spring_height_mm'], V(sx, sy, h))
        inner = Part.makeCylinder(sr-a['spring_wall'], datums['spring_height_mm'], V(sx, sy, h))
        springs.append(outer.cut(inner))
    add('KitBase', '机芯基座与三弹簧 · 平台实测／弹簧外径暂估',
        Part.makeCompound([plate.fuse(wing).removeSplitter(), *springs]))
    platter_bottom = platform_top + a['platter_bottom_above_platform']
    platter_top = platter_bottom + cfg['platter_thickness']
    add('KitPlatter', f"实测唱盘 Ø{cfg['platter_diameter']:g} × {cfg['platter_thickness']:g} mm",
        Part.makeCylinder(radius, cfg['platter_thickness'], V(cx, cy, platter_bottom)))
    rings = []
    for r in [radius * 0.3, radius * 0.54, radius * 0.72, radius - 4]:
        rings.append(Part.makeCylinder(r, 0.3, V(cx, cy, platter_top)).cut(Part.makeCylinder(r - 0.5, 0.3, V(cx, cy, platter_top))))
    add('KitMatRings', '唱盘表面环纹示意', Part.makeCompound(rings), (0.24, 0.25, 0.26))
    add('KitSpindle', '机芯主轴示意', Part.makeCylinder(3.5, 10, V(cx, cy, platter_top)), (0.72, 0.74, 0.76))
    upper_height = cfg['arm_support_height']
    pivot = V(right - 45, cy + 96, platform_top + upper_height - 10)
    add('KitArmSupport', f"唱臂支座 · 高{upper_height:g}实测／外形暂估",
        Part.makeBox(25, 33, upper_height, V(pivot.x - 12.5, pivot.y - 16.5, platform_top)))
    # User's total arm length is NOT pivot-to-stylus length. Temporarily use it
    # as the parked assembly's longitudinal span, including weight and head.
    arm_front = pivot.y + 33 - cfg['arm_total_length']
    # Two tangent circular bends keep this unmeasured outline analytic. Their
    # larger, forward position follows the curved-arm reference photograph; an
    # interpolated spline pipe produced unstable STEP volumes and slow booleans.
    bend = a['arm_bend_radius']
    y0 = cy + a['arm_bend_start_y_offset']
    yaw = a['headshell_yaw_degrees']
    exposed_connector = a['arm_connector_length'] - a['arm_connector_overlap']
    shell_template, heading, template_shell_z = headshell_shape(V(), yaw, a, 0)
    shell_front_offset_y = heading.y * exposed_connector + shell_template.BoundBox.YMin
    target_arm_end_y = arm_front - shell_front_offset_y
    # Rotating the tube downward slightly shortens its Y projection. Iterate to
    # keep the final counterweight-to-head longitudinal envelope at 250 mm.
    arm_end_y = target_arm_end_y
    for _ in range(6):
        slope = math.atan2(a['arm_front_drop'], pivot.y-arm_end_y)
        rotated_end_y = pivot.y + (arm_end_y-pivot.y) * math.cos(slope)
        arm_end_y += target_arm_end_y - rotated_end_y
    start = V(pivot.x, y0, pivot.z)
    middle = V(pivot.x+bend, y0-bend, pivot.z)
    end = V(pivot.x+2*bend, y0-2*bend, pivot.z)
    q = bend / math.sqrt(2)
    edges = [Part.makeLine(pivot, start),
             Part.Arc(start, V(pivot.x+bend-q, y0-q, pivot.z), middle).toShape(),
             Part.Arc(middle, V(pivot.x+bend+q, y0-2*bend+q, pivot.z), end).toShape(),
             Part.makeLine(end, V(pivot.x+2*bend, arm_end_y, pivot.z))]
    wire = Part.Wire(edges)
    slope = math.degrees(math.atan2(a['arm_front_drop'], pivot.y-arm_end_y))
    wire.rotate(pivot, V(1,0,0), slope)
    tangent = V(0, -math.cos(math.radians(slope)), -math.sin(math.radians(slope)))
    circle = Part.Wire(Part.makeCircle(a['arm_tube_diameter']/2, pivot, tangent))
    add('KitCurvedArm', f"弯臂停放示意 · 总长{cfg['arm_total_length']:g}非有效臂长",
        wire.makePipeShell([circle], True, False), (0.72, 0.74, 0.76))
    add('KitCounterweight', '后部配重外观示意',
        Part.makeCylinder(10, 16, V(pivot.x, pivot.y + 17, pivot.z), V(0, 1, 0)),
        (0.46, 0.47, 0.48))
    rotation = App.Rotation(V(1, 0, 0), slope)
    arm_end = pivot + rotation.multVec(V(2*bend, arm_end_y-pivot.y, 0))
    shell_rear = arm_end + heading * exposed_connector
    shell = shell_template.copy()
    shell.translate(V(shell_rear.x, shell_rear.y, arm_end.z))
    shell_z = template_shell_z + arm_end.z
    add('KitHeadshell', '参考图弯臂连接套、开槽唱头壳与指托 · 外观估算', shell)
    add('KitCartridge', '随套装唱头占位（型号待核实）',
        cartridge_shape(shell_rear, yaw, shell_z, a))
    limiter = Part.makeBox(11, 5, 8, V(pivot.x-3.5, cy+21, platform_top+17))
    rest = Part.makeCylinder(4, 27, V(pivot.x + 2, cy + 25, platform_top))
    add('KitArmRest', '停臂架与限位片示意', rest.fuse(limiter).removeSplitter())

    underbody = local_underbody(cfg, seat)
    envelope = add('UnderbodyReservation', '局部下探估算 · 电机／传动／回臂，覆盖不完整', underbody, (1.0, 0.60, 0.15), True)
    if App.GuiUp:
        envelope.ViewObject.Transparency = 65
    obstacles = section_objects(doc, *obstacle_sections)
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
    lid = doc.getObject('DustCover').Shape
    kit = section_objects(doc, 'SelectedKit')
    lid_overlap, lid_clearance = closed_cover_metrics(lid, [o.Shape for o in kit])
    roof_top = doc.getObject('AcousticRoof').Shape.optimalBoundingBox(False).ZMax
    states = []
    moving = Part.makeCompound([doc.getObject(name).Shape for name in moving_names()])
    for compression in cfg['spring_compression_range']:
        state = measurement_datums(cfg, h, compression)
        shifted_parts = []
        for obj in kit:
            shape = obj.Shape.copy()
            shape.translate(V(0, 0, state['seat_z_mm']-seat))
            shifted_parts.append((obj.Name, shape))
        bottom = local_underbody(cfg, state['seat_z_mm'])
        hits = []
        for obj in obstacles:
            if bottom.BoundBox.intersect(obj.Shape.BoundBox):
                volume = bottom.common(obj.Shape).Volume
                if volume > 1e-5:
                    hits.append(dict(part=obj.Name, overlap_mm3=round(volume, 3)))
        sweep_hits = []
        angles = sorted(set([float(n) for n in range(int(base_parameters['cover_angle_open'])+1)] +
                            [base_parameters['cover_angle_open']]))
        for angle in angles:
            lid_state = moving.copy()
            lid_state.Placement = hinge_rotation(base_parameters, angle).multiply(lid_state.Placement)
            for name, shape in shifted_parts:
                volume = interference_volume(lid_state, shape)
                if volume > 1e-5:
                    sweep_hits.append(dict(angle_degrees=angle, part=name, overlap_mm3=round(volume, 3)))
        state_overlap, state_clearance = closed_cover_metrics(lid, [shape for _, shape in shifted_parts])
        state.update(local_underbody_overlaps=hits,
                     closed_cover_clearance_mm=state_clearance,
                     closed_cover_overlap_mm3=state_overlap,
                     upper_vertical_lid_gap_mm=base_parameters['closed_height']-base_parameters['cover_wall']-state['highest_z_mm'],
                     cover_sweep_collisions=sweep_hits, cover_sweep_sample_count=len(angles),
                     roof_depth_deficit_mm=max(0, state['motor_depth_below_support_mm']-(h-roof_top)))
        states.append(state)
    study = doc.addObject('App::FeaturePython', 'StudyBasis')
    study.addProperty('App::PropertyString', 'ConfigurationJSON').ConfigurationJSON = json.dumps(cfg, ensure_ascii=False, sort_keys=True)
    study.addProperty('App::PropertyString', 'Status').Status = 'PARTIAL_MEASUREMENTS_PENDING_MOUNTING_REDESIGN'
    doc.recompute()
    report = {
        'revision': cfg['revision'], 'selected_option': cfg['selected_option'],
        'assumptions': cfg,
        'geometry_checks': {
            'local_envelope_valid': underbody.isValid(),
            **hinge_checks,
            'spring_endpoints_closed_cover_clear': all(s['closed_cover_overlap_mm3'] < 1e-5 for s in states),
            'spring_endpoints_cover_sweep_clear': all(not s['cover_sweep_collisions'] for s in states),
        },
        'hinges': hinge_metrics,
        'fit': {
            'installation_released': False,
            'dimensions_confirmed': False,
            'mounting_holes_confirmed': cfg['mounting_holes_confirmed'],
            'status': study.Status,
            'nominal_plan_mm': [cfg['nominal_width'], cfg['nominal_depth']],
            'display_datums': datums,
            'spring_states': states,
            'underbody_coverage_complete': False,
            'spring_positions_confirmed': cfg['spring_positions_confirmed'],
            'existing_roof_depth_below_mount_mm': h - roof_top,
            'additional_roof_clearance_needed_mm': max(s['roof_depth_deficit_mm'] for s in states),
            'underbody_reservation_clear': not overlaps,
            'underbody_overlaps': overlaps,
            'display_closed_cover_clear': lid_overlap < 1e-5,
            'display_cover_clearance_mm': lid_clearance,
            'illustrative_closed_cover_clear': lid_overlap < 1e-5 and all(s['closed_cover_overlap_mm3'] < 1e-5 for s in states),
            'illustrative_cover_clearance_mm': min([lid_clearance] + [s['closed_cover_clearance_mm'] for s in states]),
        },
        'limitations': ['除弯臂外用户确认与直臂图一致；部分尺寸已实测，安装接口仍未确认',
                        '局部下探体的平面位置和轮廓为估算，覆盖不完整；无重叠不证明实际无干涉，有重叠不证明实物必然碰撞',
                        '弹簧座与平台下表面共面为解释假设；0–5压缩范围不是测定行程，未包含动态余量',
                        '250总长暂作停放纵向外廓；唱臂限位角、有效臂长和播放运动未知',
                        '合页及盖总成对示意机芯做1度开盖抽样；真实机芯和自动回臂运动未验证', 'STEP 仅导出装配示意，包络及红色干涉体保留在 FCStd'],
    }
    return report


def save_report(report, root=ROOT):
    report['model_sha256'] = hashlib.sha256((root / 'cad/record-player.FCStd').read_bytes()).hexdigest()
    (root / 'cad/mechanism-fit-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


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
    save('mechanism-open.png')
    for name,original in originals.items():doc.getObject(name).Placement=original
    for name in ['Cover', 'SelectedKit', 'Controls', 'Front', 'Deck']:
        for obj in section_objects(doc, name):
            obj.ViewObject.Visibility = False
    for obj in section_objects(doc, 'Cabinet'):
        obj.ViewObject.Transparency = 75
    doc.getObject('AcousticRoof').ViewObject.Visibility = False
    doc.getObject('BearingPocket').ViewObject.Visibility = False
    for obj in section_objects(doc, 'FitAnalysis'):
        obj.ViewObject.Visibility = obj.Name in ['UnderbodyReservation', 'InterferenceAcousticRoof']
    save('mechanism-clearance.png')
    doc.getObject('AcousticRoof').ViewObject.Visibility = True
    doc.getObject('BearingPocket').ViewObject.Visibility = True
    for obj in section_objects(doc, 'FitAnalysis'):
        obj.ViewObject.Visibility = False
    for obj in section_objects(doc, 'Cabinet'):
        obj.ViewObject.Transparency = 0
    for name in ['Cover', 'SelectedKit', 'Controls', 'Front', 'Deck']:
        for obj in section_objects(doc, name):
            obj.ViewObject.Visibility = True
    doc.recompute()
    visibility = {o.Name: o.ViewObject.Visibility for o in doc.Objects if o.TypeId == 'Part::Feature'}
    for obj in doc.Objects:
        if obj.TypeId == 'Part::Feature':
            obj.ViewObject.Visibility = obj in section_objects(doc, 'SelectedKit') or obj.Name == 'UnderbodyReservation'
    view.viewRight()
    view.fitAll()
    from pivy import coin
    scene = view.getCameraNode()
    mapping, aspect = scene.viewportMapping.getValue(), scene.aspectRatio.getValue()
    scene.height.setValue(max(cfg['nominal_depth']/1.6, cfg['total_height']) * 1.15)
    scene.aspectRatio.setValue(1.6)
    scene.viewportMapping.setValue(coin.SoCamera.LEAVE_ALONE)
    Gui.updateGui()
    view.saveImage(str(ROOT / 'previews/mechanism-side.png'), 1600, 1000, 'White')
    scene.viewportMapping.setValue(mapping)
    scene.aspectRatio.setValue(aspect)
    for name, visible in visibility.items():
        doc.getObject(name).ViewObject.Visibility = visible
    view.setCameraOrientation(rotation.Q)
    view.fitAll()
