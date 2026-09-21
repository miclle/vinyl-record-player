"""Run with FreeCAD's bundled Python and library on PYTHONPATH."""
import json
import math
from pathlib import Path
import FreeCAD as App
import Part

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
        '214.2 mm 暂作为闭盖总高；原厂测量基准未明确',
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
    }
    for name in ['Woofer','TweeterLeft','TweeterRight']:
        required[name]=['Shape','DriverRole','FlangeDiameter','CutoutDiameter','ReservedDepth',
                        'TotalHeight','FlangeThickness','MountCentre','InwardAxis']
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
    checks['overall_matches_parameters']=all(abs(v-p[k])<1e-5 for v,k in zip(metrics['overall_mm'],['width','depth','closed_height']))
    drivers=[o for o in objects if hasattr(o,'DriverRole')]
    checks['one_woofer_two_tweeters']=len(drivers)==3 and sorted(o.DriverRole for o in drivers)==['tweeter','tweeter','woofer']
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
    checks['platter_diameter']=abs(doc.getObject('Platter').Shape.BoundBox.XLength-p['platter_diameter'])<1e-6
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
    boundaries=[doc.getObject(n) for n in ['SideLeft','SideRight','Bottom','Back','AcousticRoof','AcousticRear','AcousticDividerLeft','AcousticDividerRight','Baffle','FloatingDeck']]
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
        for boundary in boundaries+doc.getObject('Mechanism').Group+doc.getObject('Electronics').Group:
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
    expected=[spec['length'],spec['width'],spec['height']]
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
    metrics['woofer_floor_clearance_mm']=doc.getObject('Woofer').Shape.BoundBox.ZMin
    checks['woofer_floor_clearance']=metrics['woofer_floor_clearance_mm']>=20
    readback=Part.read(str(ROOT/'cad/lumi-three-driver.step'))
    checks['step_valid']=readback.isValid()
    checks['step_solid_count']=len(readback.Solids)==len(compound.Solids)
    checks['no_group_duplicates_in_step']=len(readback.Solids)==sum(len(o.Shape.Solids) for o in objects)
    checks['step_volume']=abs(readback.Volume-compound.Volume)/compound.Volume<1e-7
    checks['step_bounds']=all(abs(a-b)<1e-5 for a,b in zip([readback.BoundBox.XLength,readback.BoundBox.YLength,readback.BoundBox.ZLength],metrics['overall_mm']))
    return finish()

if __name__=='__main__':
    raise SystemExit(0 if validate()['passed'] else 1)
