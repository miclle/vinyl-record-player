"""Run with FreeCAD's bundled Python and library on PYTHONPATH."""
import json
import math
from pathlib import Path
import FreeCAD as App
import Part
from ac_inlet import installation as inlet_installation
from feet import installation as feet_installation

ROOT=Path(__file__).resolve().parents[1]

def validate():
    p=json.loads((ROOT/'cad/parameters.json').read_text())
    doc=App.openDocument(str(ROOT/'cad/lumi-three-driver.FCStd'))
    try:
        return _validate_document(doc,p)
    finally:
        App.closeDocument(doc.Name)


def _validate_document(doc,p):
    result={'revision':p['revision'],'freecad':'.'.join(App.Version()[:3]),'checks':{},'metrics':{},'limitations':[
        '静态 Part 实体由 JSON 驱动重建，原生文件不含自动联动的完整特征历史',
        '音响与唱盘部件为概念包络；声学、隔振、连接工艺及电气均未验证',
        '原厂 214.2 mm 测量基准未明确；本版按已购脚垫名义高度调整闭盖总高',
        '脚垫未压缩；脚座孔距、板预孔及密封为安装假设；低音离地19.5 mm，低于此前20 mm试验目标，声学待测',
        '开盖按 0 至 70 度每 5 度抽样检查，非连续运动求解',
        '未对所有零件做全局干涉放行；这里只检查列出的关键部件与外壳',
        '变压器固定耳宽厚为保守占位，孔距未知；未验证散热、磁场、电气或走线'
    ]}
    checks=result['checks'];metrics=result['metrics']
    def finish():
        result['passed']=all(checks.values())
        (ROOT/'cad/validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return result

    datum=doc.getObject('GeometryDatums')
    checks['build_parameters_match']=getattr(datum,'BuildParametersJSON','')==json.dumps(p,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    result['requested_revision']=p['revision']
    stored_parameters=getattr(datum,'BuildParametersJSON','')
    try:
        result['revision']=json.loads(stored_parameters).get('revision')
    except (ValueError,AttributeError):
        result['revision']=None
    # Reject old/incomplete model schemas before dereferencing installation properties.
    required={
        'GeometryDatums': ['BuildParametersJSON','PivotPoint','SpindlePoint','StylusPoint','CoverHinge'],
        'PowerTransformer': ['Shape'],
        'Amplifier': ['Shape'],
        'ACInlet': ['Shape','ElectricalReleased','InstallationReleased'],
        'Feet': ['Group'],
    }
    for name in ['BassPort','BearingPocket','AcousticRoof','AcousticRear','AcousticDividerLeft','AcousticDividerRight','Baffle','Bottom','Back']:
        required[name]=['Shape']
    # Slat clearance checks dereference these neighbors; reject missing parts
    # here so the failure report replaces any previous successful validation.
    for name in ['GrilleCloth','Fascia','LightChannel','LightDiffuser']:
        required[name]=['Shape']
    for name in ['Woofer','TweeterLeft','TweeterRight']:
        required[name]=['Shape','DriverRole','FlangeDiameter','CutoutDiameter','ReservedDepth',
                        'TotalHeight','FlangeThickness','MountCentre','InwardAxis']
    for i in range(4):
        for prefix in ('Foot','FootMount'):
            required[f'{prefix}{i}']=['Shape','InstallationReleased']
    missing=[]
    for name,properties in required.items():
        obj=doc.getObject(name)
        if obj is None:
            missing.append(name)
        else:
            missing.extend(name+'.'+prop for prop in properties if not hasattr(obj,prop))
    checks['required_model_fields_present']=not missing
    if not checks['build_parameters_match'] or missing:
        result['errors']=[]
        if not checks['build_parameters_match']:
            result['errors'].append('模型参数快照缺失、无效或与当前参数不一致，请重新生成模型')
        if missing:
            result['errors'].append('模型缺少必需对象或属性：'+', '.join(missing))
        return finish()
    objects=[o for o in doc.Objects if o.TypeId=='Part::Feature' and not o.Shape.isNull()]
    checks['all_shapes_valid']=all(o.Shape.isValid() and len(o.Shape.Solids)>0 for o in objects)
    compound=Part.makeCompound([o.Shape for o in objects]);bb=compound.BoundBox
    metrics['part_count']=len(objects);metrics['solid_count']=len(compound.Solids)
    metrics['overall_mm']=[bb.XLength,bb.YLength,bb.ZLength]
    expected_overall=[p['width'],p['depth']+p['ac_inlet']['flange_thickness'],p['closed_height']]
    checks['overall_matches_parameters']=all(abs(v-e)<1e-5 for v,e in zip(metrics['overall_mm'],expected_overall))
    drivers=[o for o in objects if hasattr(o,'DriverRole')]
    checks['one_woofer_two_fullrange']=len(drivers)==3 and sorted(o.DriverRole for o in drivers)==['fullrange','fullrange','woofer']
    metrics['driver_reservations_mm']={o.Name:{'role':o.DriverRole,'flange_diameter':float(o.FlangeDiameter),'cutout_diameter':float(o.CutoutDiameter),'depth':float(o.ReservedDepth),'total_height':float(o.TotalHeight),'flange_thickness':float(o.FlangeThickness)} for o in drivers}
    checks['driver_dimensions_match_parameters']=all(all(abs(float(getattr(o,prop))-p[o.DriverRole][key])<1e-6 for prop,key in [('FlangeDiameter','flange_diameter'),('CutoutDiameter','cutout_diameter'),('TotalHeight','total_height'),('FlangeThickness','flange_thickness')]) for o in drivers)
    # Rotate each saved shape to its own axis; tilted tweeter world bounds are not its height.
    driver_bounds={}
    for o in drivers:
        aligned=o.Shape.copy()
        aligned.Placement=App.Placement(App.Vector(),App.Rotation(o.InwardAxis,App.Vector(0,0,1))).multiply(aligned.Placement)
        bounds=aligned.optimalBoundingBox(False)
        driver_bounds[o.Name]=[bounds.XLength,bounds.YLength,bounds.ZLength]
    metrics['driver_local_bounds_mm']=driver_bounds
    checks['driver_geometry_matches_dimensions']=all(
        all(abs(actual-expected)<1e-5 for actual,expected in zip(driver_bounds[o.Name],
            [p[o.DriverRole]['flange_diameter']]*2+[p[o.DriverRole]['total_height']]))
        and abs(float(o.ReservedDepth)+float(o.FlangeThickness)-float(o.TotalHeight))<1e-6
        for o in drivers)
    metrics['pivot_distance_mm']=(datum.PivotPoint-datum.SpindlePoint).Length
    metrics['effective_length_mm']=(datum.StylusPoint-datum.PivotPoint).Length
    metrics['stylus_radius_mm']=(datum.StylusPoint-datum.SpindlePoint).Length
    checks['pivot_distance']=abs(metrics['pivot_distance_mm']-p['pivot_distance'])<1e-6
    checks['effective_arm_length']=abs(metrics['effective_length_mm']-p['arm_effective_length'])<1e-6
    checks['platter_diameter']=abs(doc.getObject('Platter').Shape.optimalBoundingBox(False).XLength-p['platter_diameter'])<1e-6
    stationary=doc.getObject('Cabinet').Group+doc.getObject('Mechanism').Group+doc.getObject('Deck').Group
    lid=doc.getObject('DustCover').Shape
    def volume(a,b):
        if not a.BoundBox.intersect(b.BoundBox):return 0.0
        return a.common(b).Volume
    closed_intersections={o.Name:volume(lid,o.Shape) for o in stationary}
    checks['cover_closed_no_interference']=all(v<1e-5 for v in closed_intersections.values())
    metrics['cover_closed_intersections_mm3']={k:v for k,v in closed_intersections.items() if v>1e-5}
    mechanisms=Part.makeCompound([o.Shape for o in doc.getObject('Mechanism').Group])
    metrics['cover_to_mechanism_min_distance_mm']=lid.distToShape(mechanisms)[0]
    collisions=[]
    for angle in range(0,int(p['cover_angle_open'])+1,5):
        moved=lid.copy();moved.rotate(datum.CoverHinge,App.Vector(1,0,0),-angle)
        for o in stationary:
            v=volume(moved,o.Shape)
            if v>1e-5:collisions.append({'angle':angle,'part':o.Name,'volume_mm3':v})
    checks['cover_sweep_samples_clear']=not collisions
    metrics['cover_sweep_collisions']=collisions
    internal_envelopes=drivers+[doc.getObject(n) for n in ['MotorEnvelope','BearingEnvelope','Amplifier','PhonoBoard']]
    boundaries=[doc.getObject(n) for n in ['SideLeft','SideRight','Bottom','Back','AcousticRoof','AcousticRear','AcousticDividerLeft','AcousticDividerRight','Baffle','FloatingDeck','BearingPocket']]
    bad=[]
    for obj in internal_envelopes:
        for boundary in boundaries:
            v=volume(obj.Shape,boundary.Shape)
            if v>1e-5:bad.append({'part':obj.Name,'boundary':boundary.Name,'volume_mm3':v})
    checks['internal_envelopes_clear']=not bad;metrics['internal_collisions']=bad
    # Check solid cylinders, not just thin visual cones, to reserve mounting space.
    reserved=[]
    for o in drivers:
        c=o.MountCentre;axis=o.InwardAxis
        full=Part.makeCylinder(float(o.CutoutDiameter)/2,float(o.ReservedDepth),c,axis).fuse(Part.makeCylinder(float(o.FlangeDiameter)/2,float(o.FlangeThickness),c-axis*float(o.FlangeThickness),axis))
        reserved.append((o.Name,full))
    reservation_collisions=[]
    for name,shape in reserved:
        for boundary in boundaries+[doc.getObject('BassPort')]+doc.getObject('Mechanism').Group+doc.getObject('Electronics').Group:
            v=volume(shape,boundary.Shape)
            if v>1e-5:reservation_collisions.append({'part':name,'boundary':boundary.Name,'volume_mm3':v})
    for i,(name,shape) in enumerate(reserved):
        for other,other_shape in reserved[i+1:]:
            v=volume(shape,other_shape)
            if v>1e-5:reservation_collisions.append({'part':name,'boundary':other,'volume_mm3':v})
    checks['solid_installation_reservations_clear']=not reservation_collisions
    metrics['installation_reservation_collisions']=reservation_collisions
    transformer=doc.getObject('PowerTransformer')
    spec=p['power_transformer']
    bb=transformer.Shape.optimalBoundingBox(False)
    metrics['transformer_envelope_mm']=[bb.XLength,bb.YLength,bb.ZLength]
    expected=[spec['mount_span'],spec['body_width'],spec['body_height']]
    # Above the assumed feet, the saved solid must retain the body cross section.
    section_z=p['foot_height']+p['wall']+spec['body_height']/2
    section=transformer.Shape.common(Part.makeBox(p['width'],p['depth'],0.1,App.Vector(0,0,section_z)))
    section_bb=section.optimalBoundingBox(False)
    checks['transformer_dimensions_match']=all(abs(a-b)<1e-5 for a,b in zip(metrics['transformer_envelope_mm'],expected)) and all(
        abs(a-b)<1e-5 for a,b in zip([section_bb.XLength,section_bb.YLength],[spec['body_length'],spec['body_width']]))
    checks['transformer_mount_on_floor']=abs(bb.ZMin-(p['foot_height']+p['wall']))<1e-5
    # Reserve the entire 88 x 55 x 50 box, including space above the ears.
    envelope=Part.makeBox(*expected,App.Vector(bb.XMin,bb.YMin,bb.ZMin))
    transformer_hits=[]
    transformer_gaps={}
    for obj in objects:
        if obj.Name==transformer.Name:continue
        v=volume(envelope,obj.Shape)
        if v>1e-5:transformer_hits.append({'part':obj.Name,'volume_mm3':v})
        if obj.Name in ['Amplifier','PhonoBoard','FloatingDeck','RearSupport']:
            transformer_gaps[obj.Name]=envelope.distToShape(obj.Shape)[0]
    metrics['transformer_reservation_collisions']=transformer_hits
    metrics['transformer_clearances_mm']=transformer_gaps
    checks['transformer_reservation_clear']=not transformer_hits
    amplifier=doc.getObject('Amplifier')
    spec=p['amplifier']
    bb=amplifier.Shape.optimalBoundingBox(False)
    metrics['amplifier_envelope_mm']=[bb.XLength,bb.YLength,bb.ZLength]
    expected=([spec['width'],spec['length'],spec['height']] if spec['rotation_degrees']==90 else [spec['length'],spec['width'],spec['height']])
    checks['amplifier_dimensions_match']=all(abs(a-b)<1e-5 for a,b in zip(metrics['amplifier_envelope_mm'],expected))
    amplifier_hits=[]
    amplifier_gaps={}
    for obj in objects:
        if obj.Name==amplifier.Name:continue
        v=volume(amplifier.Shape,obj.Shape)
        if v>1e-5:amplifier_hits.append({'part':obj.Name,'volume_mm3':v})
        if obj.Name in ['PowerTransformer','Bottom','SideRight','Back','FloatingDeck','RearSupport']:
            amplifier_gaps[obj.Name]=amplifier.Shape.distToShape(obj.Shape)[0]
    metrics['amplifier_reservation_collisions']=amplifier_hits
    metrics['amplifier_clearances_mm']=amplifier_gaps
    checks['amplifier_reservation_clear']=not amplifier_hits
    inlet_checks,inlet_metrics=check_ac_inlet(doc,p)
    checks.update(inlet_checks);metrics['ac_inlet']=inlet_metrics
    feet_checks,feet_metrics=check_feet(doc,p)
    checks.update(feet_checks);metrics['feet']=feet_metrics
    wood_checks,wood_metrics=check_woodworking(doc,p)
    checks.update(wood_checks);metrics['woodworking']=wood_metrics
    acoustic_checks,acoustic_metrics=check_acoustics(doc,p,reserved+[(transformer.Name,envelope)])
    checks.update(acoustic_checks);metrics['acoustics']=acoustic_metrics
    metrics['woofer_floor_clearance_mm']=doc.getObject('Woofer').Shape.optimalBoundingBox(False).ZMin
    metrics['woofer_previous_20mm_trial_target_met']=metrics['woofer_floor_clearance_mm']>=20
    checks['woofer_floor_clearance_matches_installation']=(metrics['woofer_floor_clearance_mm']>0 and
        abs(metrics['woofer_floor_clearance_mm']-(p['foot_height']-p['woofer']['flange_thickness']))<1e-5)
    readback=Part.read(str(ROOT/'cad/lumi-three-driver.step'))
    checks['step_valid']=readback.isValid()
    checks['step_solid_count']=len(readback.Solids)==len(compound.Solids)
    checks['no_group_duplicates_in_step']=len(readback.Solids)==sum(len(o.Shape.Solids) for o in objects)
    checks['step_volume']=abs(readback.Volume-compound.Volume)/compound.Volume<1e-7
    checks['step_bounds']=all(abs(a-b)<1e-5 for a,b in zip([readback.BoundBox.XLength,readback.BoundBox.YLength,readback.BoundBox.ZLength],metrics['overall_mm']))
    return finish()

def check_feet(doc,p):
    parts=feet_installation(p)
    s=p['feet'];bottom=doc.Bottom.Shape
    matches=True;cutouts_match=True;supported=True;hits=[]
    for i,part in enumerate(parts):
        x,y=part['center'];r=s['flange_diameter']/2
        region=Part.makeCylinder(r,p['wall'],App.Vector(x,y,p['foot_height']))
        expected=region
        for cutter in part['cutouts']:
            expected=expected.cut(cutter)
        actual=bottom.common(region)
        cutouts_match &= actual.cut(expected).Volume+expected.cut(actual).Volume<1e-5
        supported &= (x-r>=p['wall'] and x+r<=p['width']-p['wall'] and
                      y-r>=0 and y+r<=p['depth'] and actual.Volume>0)
        for prefix,key in [('Foot','foot'),('FootMount','mount')]:
            name=f'{prefix}{i}';obj=doc.getObject(name)
            if obj is None:
                matches=False
                continue
            shape=obj.Shape
            matches &= shape.cut(part[key]).Volume+part[key].cut(shape).Volume<1e-5
            for other in doc.Objects:
                if other.TypeId!='Part::Feature' or other.Name==name:
                    continue
                if shape.BoundBox.intersect(other.Shape.BoundBox) and shape.common(other.Shape).Volume>1e-5:
                    hits.append({'part':name,'other':other.Name})
    return {'feet_parts_match':bool(matches),'feet_bottom_cutouts_match':bool(cutouts_match),
            'feet_installation_clear':not hits,'feet_flanges_supported':bool(supported)}, {
        'centers_xy_mm':[list(part['center']) for part in parts],
        'mount_pilot_centers_xy_mm':[[list(xy) for xy in part['holes']] for part in parts],
        'nominal_uncompressed_floor_height_mm':p['foot_height'],
        'nominal_thread_overlap_mm':s['flange_thickness']+s['barrel_height'],
        'stud_protrusion_above_mount_mm':s['stud_length']-s['flange_thickness']-s['barrel_height'],
        'pilot_remaining_wood_mm':p['wall']-s['pilot_depth_assumption'],
        'collisions':hits,'installation_released':False,
        'note':'螺纹为名义圆柱，啮合是包络重叠长度；底盘贴板及橡胶贴底盘为理想接触，未验证真实密封或承载'}


def check_ac_inlet(doc,p):
    opening, bolts, expected, wiring = inlet_installation(p)
    actual = doc.getObject('ACInlet').Shape
    back = doc.getObject('Back').Shape
    s = p['ac_inlet']
    # Compare all removed material inside a local region: catches filled,
    # oversize and misplaced holes, as well as accidentally squared R3 corners.
    region = Part.makeBox(s['flange_width']+2, p['wall'], s['flange_height']+2,
                         App.Vector(s['center_x']-s['flange_width']/2-1, p['depth']-p['wall'],
                                    s['center_z']-s['flange_height']/2-1))
    desired = region.cut(opening)
    for bolt in bolts:
        desired = desired.cut(bolt)
    saved = back.common(region)
    cutouts_match = saved.cut(desired).Volume + desired.cut(saved).Volume < 1e-5
    hits, wire_hits, gaps = [], [], {}
    for obj in doc.Objects:
        if obj.TypeId != 'Part::Feature' or obj.Name == 'ACInlet':
            continue
        if actual.common(obj.Shape).Volume > 1e-5:
            hits.append(obj.Name)
        if wiring.common(obj.Shape).Volume > 1e-5:
            wire_hits.append(obj.Name)
        if obj.Name in ('PowerTransformer','RearSupport','FloatingDeck','AcousticDividerLeft'):
            gaps[obj.Name] = wiring.distToShape(obj.Shape)[0]
    checks = {
        'ac_inlet_panel_cutouts_match': cutouts_match,
        'ac_inlet_envelope_matches': actual.cut(expected).Volume + expected.cut(actual).Volume < 1e-5,
        'ac_inlet_envelope_clear': not hits,
        'ac_inlet_wiring_space_clear': not wire_hits,
        'ac_inlet_flange_supported': desired.Volume > 0 and region.common(back).Volume > 0
            and s['center_x']-s['flange_width']/2 > p['wall']
            and s['center_x']+s['flange_width']/2 < p['width']-p['wall']
            and s['center_z']-s['flange_height']/2 > p['foot_height']+p['wall']
            and s['center_z']+s['flange_height']/2 < p['cabinet_top'],
    }
    return checks, {'center_xz_mm':[s['center_x'],s['center_z']],
                    'cutout_width_height_radius_mm':[s['cutout_width'],s['cutout_height'],s['cutout_radius']],
                    'bolt_centers_xz_mm':[[s['center_x'],s['center_z']+sign*s['mount_hole_pitch']/2] for sign in (-1,1)],
                    'collisions':hits,'wire_reservation_collisions':wire_hits,
                    'wire_reservation_clearances_mm':gaps,
                    'wire_clearance_assumption_mm':s['wire_clearance_assumption'],
                    'electrical_released':False,'installation_released':False}


def check_acoustics(doc,p,reserved):
    """Measure enclosed saved geometry with only the intended driver/port holes capped.

    Net volume subtracts solid installation envelopes, not hollow visual baskets;
    it is a conservative layout estimate, not an acoustic measurement of the drivers.
    """
    V=App.Vector
    W,D,H=p['width'],p['depth'],p['cabinet_top']
    t=p['wall']; z0=p['foot_height']; ac=p['acoustic']; port=p['bass_port']
    zlo,zhi=z0+t,ac['roof_bottom_z']
    def obj(name):return doc.getObject(name).Shape
    a=math.radians(p['front_angle'])
    front_y=lambda z:8+(z-zlo)/math.tan(a)
    inner_offset=8+ac['baffle_thickness']/math.sin(a)
    pts=[V(t,front_y(zlo)+8,zlo),V(t,front_y(zhi)+8,zhi),
         V(t,front_y(zhi)+inner_offset,zhi),V(t,front_y(zlo)+inner_offset,zlo)]
    blank_baffle=Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(W-2*t,0,0))
    blank_bottom=Part.makeBox(W-2*t,D,t,V(t,0,z0))
    caps=[]
    for name in ['Woofer','TweeterLeft','TweeterRight']:
        driver=doc.getObject(name)
        cutter=Part.makeCylinder(float(driver.CutoutDiameter)/2,30,
                                driver.MountCentre-driver.InwardAxis*5,driver.InwardAxis)
        caps.append(cutter.common(blank_bottom if name=='Woofer' else blank_baffle))
    px,pz=port['center_x'],port['center_z']; pr=port['inner_diameter']/2
    outer_r=pr+port['wall_thickness']
    caps.append(Part.makeCylinder(outer_r,t,V(px,D-t,pz),V(0,1,0)))
    caps.append(Part.makeCylinder(port['flange_diameter']/2,port['flange_thickness'],
                                 V(px,D-port['flange_thickness'],pz),V(0,1,0)))
    walls=[obj(n) for n in ['SideLeft','SideRight','Bottom','Back','Baffle','AcousticRoof',
                           'AcousticRear','AcousticDividerLeft','AcousticDividerRight','BearingPocket']]
    # Purchased assemblies close the new panel openings in the nominal CAD.
    # Do not cap missing mounts: a real saved-geometry leak must still fail.
    walls.extend(o.Shape for o in doc.Feet.Group)
    barrier=walls[0].multiFuse(walls[1:]+caps)
    # The outside remains connected; closed acoustic voids form separate solids.
    region=Part.makeBox(W+4,D+4,H+4,V(-2,-2,-2))
    air=region.cut(barrier)
    # Locate each chamber from its current boundaries, not the original layout.
    left,right=p['acoustic_divider_x']; pt=ac['partition_thickness']
    seed_z=(zlo+zhi)/2
    inner_front=front_y(seed_z)+inner_offset
    satellite_y=(inner_front+ac['satellite_rear_y'])/2
    seeds={'left':V((t+left)/2,satellite_y,seed_z),
           'woofer':V((left+pt+right)/2,(inner_front+D-t)/2,seed_z),
           'right':V((right+pt+W-t)/2,satellite_y,seed_z)}
    candidates={key:[i for i,solid in enumerate(air.Solids) if solid.isInside(seed,1e-6,False)]
                for key,seed in seeds.items()}
    sealed=all(len(ids)==1 for ids in candidates.values())
    if sealed:
        indices=[ids[0] for ids in candidates.values()]
        sealed=len(set(indices))==3 and all(air.Solids[i].BoundBox.XMin>0 and
            air.Solids[i].BoundBox.YMin>0 and air.Solids[i].BoundBox.ZMin>0 for i in indices)
    checks={'three_independent_enclosed_chambers':sealed}
    metrics={'volume_basis':'保存实体封闭性检测；仅临时封住设计的扬声器及倒相口。脚座穿板由保存的脚垫与固定座理想接触封闭，不代表实物气密。净容积扣除所有已建模占用，扬声器与变压器采用实心安装包络，倒相管扣除整个外廓；重叠占用只扣一次。未计尚未建模的吸音材料、支柱、密封件及线缆。',
             'acoustic_performance_verified':False,'chambers':{},'port_inner_diameter_mm':port['inner_diameter'],
             'port_length_mm':port['length'],'port_trial_lengths_mm':port['trial_lengths']}
    port_outer=Part.makeCylinder(outer_r,port['length'],V(px,D-port['length'],pz),V(0,1,0))
    objects=[o for o in doc.Objects if o.TypeId=='Part::Feature']
    replaced_names={name for name,_ in reserved}|{'BassPort'}
    occupants=[o.Shape for o in objects if o.Name not in replaced_names]
    occupants.extend(shape for _,shape in reserved)
    occupants.append(port_outer)
    if sealed:
        for key,ids in candidates.items():
            cavity=air.Solids[ids[0]]
            net=cavity
            # Boolean subtraction counts overlapping reservations only once.
            for shape in occupants:
                if net.BoundBox.intersect(shape.BoundBox):
                    net=net.cut(shape)
            metrics['chambers'][key]={'gross_after_recess_l':cavity.Volume/1e6,
                                     'conservative_net_l':net.Volume/1e6}
    port_hits=[]
    for o in objects:
        if o.Name=='BassPort':continue
        overlap=obj('BassPort').common(o.Shape).Volume
        if overlap>1e-5:port_hits.append({'part':o.Name,'volume_mm3':overlap})
    bounds=obj('BassPort').optimalBoundingBox(False)
    expected_volume=math.pi*((outer_r**2-pr**2)*(port['length']-port['flange_thickness'])+
                            ((port['flange_diameter']/2)**2-pr**2)*port['flange_thickness'])
    checks['bass_port_dimensions_match']=all(abs(a-b)<1e-5 for a,b in zip(
        [bounds.XMin,bounds.YMin,bounds.ZMin,bounds.XLength,bounds.YLength,bounds.ZLength],
        [px-port['flange_diameter']/2,D-port['length'],pz-port['flange_diameter']/2,
         port['flange_diameter'],port['length'],port['flange_diameter']])) and abs(obj('BassPort').Volume-expected_volume)<1e-4
    checks['bass_port_solid_clear']=not port_hits
    metrics['port_collisions']=port_hits
    # Reject a blocked tube or a blocked one-diameter approach at its inner mouth.
    path=Part.makeCylinder(pr,port['length']+port['inner_diameter'],
                           V(px,D-port['length']-port['inner_diameter'],pz),V(0,1,0))
    path_hits=[o.Name for o in objects if path.common(o.Shape).Volume>1e-5]
    path_hits.extend(name+' installation envelope' for name,shape in reserved if path.common(shape).Volume>1e-5)
    checks['bass_port_air_path_clear']=not path_hits
    metrics['port_air_path_obstructions']=path_hits
    checks['bass_port_connects_only_woofer']=False
    if sealed:
        mouth=V(px,D-port['length']-1,pz)
        checks['bass_port_connects_only_woofer']=air.Solids[candidates['woofer'][0]].isInside(mouth,1e-6,False)
    return checks,metrics


def check_woodworking(doc,p):
    """Check real saved solids against nominal thickness and rectangular stock."""
    normal=App.Vector(0,math.sin(math.radians(p['front_angle'])),-math.cos(math.radians(p['front_angle'])))
    metrics={}; thickness_ok=True; stock_ok=True
    expected=['SideLeft','SideRight','Bottom','Back','Baffle','AcousticRoof',
              'AcousticRear','AcousticDividerLeft','AcousticDividerRight','RearSupport','FloatingDeck']
    expected += [f'Slat{i+1:02}' for i in range(p['slat_count'])]
    for name in expected:
        obj=doc.getObject(name)
        if obj is None or not all(hasattr(obj,k) for k in ['StockLength','StockWidth','StockThickness','StockNormal','StockCount']):
            thickness_ok=stock_ok=False
            metrics[name]={'error':'缺少备料或法向厚度字段'}
            continue
        thickness=float(obj.StockThickness)
        direction=obj.StockNormal
        if name=='Baffle':thickness=p['acoustic']['baffle_thickness'];direction=normal
        if name.startswith('Slat'):thickness=p['slat_thickness'];direction=normal
        dims=[]
        for solid in obj.Shape.Solids:
            aligned=solid.copy()
            aligned.Placement=App.Placement(App.Vector(),App.Rotation(direction,App.Vector(0,0,1))).multiply(aligned.Placement)
            bb=aligned.optimalBoundingBox(False)
            length,width=sorted([bb.XLength,bb.YLength],reverse=True)
            dims.append([length,width,bb.ZLength])
            thickness_ok &= abs(bb.ZLength-thickness)<1e-5 and abs(float(obj.StockThickness)-thickness)<1e-6
            stock_ok &= length<=float(obj.StockLength)+1e-5 and width<=float(obj.StockWidth)+1e-5
        stock=[float(obj.StockLength),float(obj.StockWidth),float(obj.StockThickness)]
        stock_ok &= all(abs(v-round(v))<1e-6 for v in stock) and obj.StockCount==len(dims)
        metrics[name]={'finished_local_bounds_mm':dims,'rectangular_stock_mm':stock,'quantity':obj.StockCount}
    slats=[doc.getObject(f'Slat{i+1:02}') for i in range(p['slat_count'])]
    regular=all(s and s.Shape.isValid() for s in slats)
    if regular:
        regular=all(abs(s.Shape.Volume-(p['width']-2*p['wall'])*p['slat_face_width']*p['slat_thickness'])<1e-5 for s in slats)
        regular &= all(abs(slats[i].Shape.CenterOfMass.z-slats[i-1].Shape.CenterOfMass.z-p['slat_pitch'])<1e-6 for i in range(1,len(slats)))
        for slat in slats:
            for other in [doc.GrilleCloth,doc.Fascia,doc.Bottom,doc.Baffle,doc.LightChannel,doc.LightDiffuser]+slats:
                if slat.Name!=other.Name:
                    regular &= slat.Shape.common(other.Shape).Volume<1e-5
    return {'wood_panel_normal_thickness_matches':bool(thickness_ok),
            'integer_wood_stock_contains_finished_panels':bool(stock_ok),
            'rectangular_slats_pitch_and_clearance':bool(regular)},metrics


if __name__=='__main__':
    raise SystemExit(0 if validate()['passed'] else 1)
