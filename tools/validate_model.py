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
    objects=[o for o in doc.Objects if o.TypeId=='Part::Feature' and not o.Shape.isNull()]
    result={'revision':p['revision'],'freecad':'.'.join(App.Version()[:3]),'checks':{},'metrics':{},'limitations':[
        '静态 Part 实体由 JSON 驱动重建，原生文件不含自动联动的完整特征历史',
        '音响与唱盘部件为概念包络；声学、隔振、连接工艺及电气均未验证',
        '214.2 mm 暂作为闭盖总高；原厂测量基准未明确',
        '开盖按 0 至 70 度每 5 度抽样检查，非连续运动求解',
        '未对所有零件做全局干涉放行；这里只检查列出的关键部件与外壳'
    ]}
    checks=result['checks'];metrics=result['metrics']
    checks['all_shapes_valid']=all(o.Shape.isValid() and len(o.Shape.Solids)>0 for o in objects)
    compound=Part.makeCompound([o.Shape for o in objects]);bb=compound.BoundBox
    metrics['part_count']=len(objects);metrics['solid_count']=len(compound.Solids)
    metrics['overall_mm']=[bb.XLength,bb.YLength,bb.ZLength]
    checks['overall_matches_parameters']=all(abs(v-p[k])<1e-5 for v,k in zip(metrics['overall_mm'],['width','depth','closed_height']))
    drivers=[o for o in objects if hasattr(o,'DriverRole')]
    checks['one_woofer_two_tweeters']=len(drivers)==3 and sorted(o.DriverRole for o in drivers)==['tweeter','tweeter','woofer']
    metrics['driver_reservations_mm']={o.Name:{'role':o.DriverRole,'flange_diameter':float(o.FlangeDiameter),'cutout_diameter':float(o.CutoutDiameter),'depth':float(o.ReservedDepth)} for o in drivers}
    checks['driver_dimensions_match_parameters']=all(all(abs(float(getattr(o,prop))-p[o.DriverRole][key])<1e-6 for prop,key in [('FlangeDiameter','flange_diameter'),('CutoutDiameter','cutout_diameter'),('ReservedDepth','depth')]) for o in drivers)
    datum=doc.getObject('GeometryDatums')
    checks['build_parameters_match']=getattr(datum,'BuildParametersJSON','')==json.dumps(p,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    result['requested_revision']=p['revision']
    stored_parameters=getattr(datum,'BuildParametersJSON','')
    try:
        result['revision']=json.loads(stored_parameters).get('revision')
    except (ValueError,AttributeError):
        result['revision']=None
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
        full=Part.makeCylinder(float(o.CutoutDiameter)/2,float(o.ReservedDepth),c,axis).fuse(Part.makeCylinder(float(o.FlangeDiameter)/2,3,c-axis*3,axis))
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
    metrics['woofer_floor_clearance_mm']=doc.getObject('Woofer').Shape.BoundBox.ZMin
    checks['woofer_floor_clearance']=metrics['woofer_floor_clearance_mm']>=20
    readback=Part.read(str(ROOT/'cad/lumi-three-driver.step'))
    checks['step_valid']=readback.isValid()
    checks['step_solid_count']=len(readback.Solids)==len(compound.Solids)
    checks['no_group_duplicates_in_step']=len(readback.Solids)==sum(len(o.Shape.Solids) for o in objects)
    checks['step_volume']=abs(readback.Volume-compound.Volume)/compound.Volume<1e-7
    checks['step_bounds']=all(abs(a-b)<1e-5 for a,b in zip([readback.BoundBox.XLength,readback.BoundBox.YLength,readback.BoundBox.ZLength],metrics['overall_mm']))
    result['passed']=all(checks.values())
    (ROOT/'cad/validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    App.closeDocument(doc.Name)
    return result

if __name__=='__main__':
    raise SystemExit(0 if validate()['passed'] else 1)
