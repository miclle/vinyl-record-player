"""Refresh native Bambu project meshes while preserving its printer and filament settings."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile,ZIP_DEFLATED

import FreeCAD
import Mesh

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/3d-print/control-panel'
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
PROD='http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
ET.register_namespace('',NS)
ET.register_namespace('p',PROD)
ET.register_namespace('BambuStudio','http://schemas.bambulab.com/package/2021')


def refresh(path):
    path=Path(path)
    with ZipFile(path) as archive:
        files={name:archive.read(name) for name in archive.namelist()}
    model=ET.fromstring(files['3D/3dmodel.model'])
    config=ET.fromstring(files['Metadata/model_settings.config'])
    components=model.findall(f'.//{{{NS}}}component')
    if len(components)!=2:raise ValueError('Expected one panel and one lettering component')
    check=[]
    mesh_documents={}
    for component,filename,extruder in zip(components,('Control-panel.stl','Control-panel-markings.stl'),('1','2')):
        transform=[float(v) for v in component.get('transform').split()]
        if transform[:9]!=[1,0,0,0,1,0,0,0,1]:raise ValueError('Expected translation-only native component')
        member=component.get(f'{{{PROD}}}path').lstrip('/')
        root=mesh_documents.setdefault(member,ET.fromstring(files[member]))
        obj=root.find(f'.//{{{NS}}}object[@id="{component.get("objectid")}"]')
        mesh=Mesh.Mesh(str(OUT/filename))
        vertices,facets=mesh.Topology
        obj.remove(obj.find(f'{{{NS}}}mesh'))
        element=ET.SubElement(obj,f'{{{NS}}}mesh')
        vv=ET.SubElement(element,f'{{{NS}}}vertices')
        for vertex in vertices:
            ET.SubElement(vv,f'{{{NS}}}vertex',{key:format(value-offset,'.12g')
                 for key,value,offset in zip(('x','y','z'),vertex,transform[9:])})
        tt=ET.SubElement(element,f'{{{NS}}}triangles')
        for facet in facets:ET.SubElement(tt,f'{{{NS}}}triangle',dict(zip(('v1','v2','v3'),map(str,facet))))
        part=config.find(f'object/part[@id="{component.get("objectid")}"]')
        if part.find('metadata[@key="extruder"]').get('value')!=extruder:raise ValueError('Filament assignment differs')
        part.find('mesh_stat').set('face_count',str(mesh.CountFacets))
        check.append({'source':filename,'triangles':mesh.CountFacets,'extruder':int(extruder)})
    config.find('object/metadata[@face_count]').set('face_count',str(sum(v['triangles'] for v in check)))
    for name in ('ModificationDate',):
        model.find(f'{{{NS}}}metadata[@name="{name}"]').text='2026-10-10'
    for member,root in mesh_documents.items():files[member]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    files['3D/3dmodel.model']=ET.tostring(model,encoding='utf-8',xml_declaration=True)
    files['Metadata/model_settings.config']=ET.tostring(config,encoding='utf-8',xml_declaration=True)
    settings=json.loads(files['Metadata/project_settings.config'])
    fine=settings['nozzle_diameter']==['0.2']
    settings.update(layer_height='0.1' if fine else '0.2',
                    top_shell_layers='8' if fine else '4',top_shell_thickness='0.8',
                    top_surface_pattern='monotonicline',top_surface_speed=['30','30'],
                    ironing_type='no ironing',enable_support='0',wall_generator='arachne',
                    wipe_tower_x=['180'])
    files['Metadata/project_settings.config']=json.dumps(settings,ensure_ascii=False,indent=2).encode()
    # Retire all prior slice results and thumbnails after geometry or settings change.
    for member in list(files):
        if member.startswith('Metadata/') and (member.endswith(('.png','.json')) and member!='Metadata/project_settings.config'
            or member=='Metadata/slice_info.config'):
            del files[member]
    target=path.with_suffix('.new.3mf')
    with ZipFile(target,'w',ZIP_DEFLATED) as archive:
        for member,data in files.items():archive.writestr(member,data)
    target.replace(path)
    return verify(path)


def verify(path):
    with ZipFile(path) as archive:
        if archive.testzip():raise ValueError('Invalid project ZIP')
        model=ET.fromstring(archive.read('3D/3dmodel.model'))
        config=ET.fromstring(archive.read('Metadata/model_settings.config'))
        settings=json.loads(archive.read('Metadata/project_settings.config'))
        checks=[]
        components=model.findall(f'.//{{{NS}}}component')
        if len(components)!=2:raise ValueError('Expected exactly two native parts')
        for component,filename,extruder in zip(components,
                         ('Control-panel.stl','Control-panel-markings.stl'),('1','2')):
            transform=[float(v) for v in component.get('transform').split()]
            member=component.get(f'{{{PROD}}}path').lstrip('/')
            root=ET.fromstring(archive.read(member))
            obj=root.find(f'.//{{{NS}}}object[@id="{component.get("objectid")}"]')
            vertices=[tuple(float(v.get(key))+offset for key,offset in zip(('x','y','z'),transform[9:]))
                      for v in obj.findall(f'{{{NS}}}mesh/{{{NS}}}vertices/{{{NS}}}vertex')]
            facets=[tuple(int(v.get(key)) for key in ('v1','v2','v3'))
                    for v in obj.findall(f'{{{NS}}}mesh/{{{NS}}}triangles/{{{NS}}}triangle')]
            source_vertices,source_facets=Mesh.Mesh(str(OUT/filename)).Topology
            if len(vertices)!=len(source_vertices) or facets!=[tuple(f) for f in source_facets]:
                raise ValueError('Native triangle topology differs from current STL')
            delta=max(abs(a-b) for v,w in zip(vertices,source_vertices) for a,b in zip(v,w))
            if delta>1e-6:raise ValueError('Native world vertices differ from current STL')
            part=config.find(f'object/part[@id="{component.get("objectid")}"]')
            if part.find('metadata[@key="extruder"]').get('value')!=extruder:raise ValueError('Incorrect material')
            checks.append(dict(source=filename,vertex_difference_mm=delta,triangle_indices_match=True,extruder=int(extruder)))
        return dict(passed=True,project=Path(path).name,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                    checked_on='2026-10-10',geometry_readback=checks,filament_colour=settings['filament_colour'],
                    nozzle_diameter=settings['nozzle_diameter'],layer_height=settings['layer_height'],
                    gui_slice_completed=False,gcode_included=False,
                    print_orientation='Flat rear on bed; front upwards',
                    plate_thickness_mm=3.5,raised_markings_height_mm=0.4,total_height_mm=3.9,
                    top_shell_layers=settings['top_shell_layers'],top_shell_thickness=settings['top_shell_thickness'],
                    top_surface_pattern=settings['top_surface_pattern'],top_surface_speed=settings['top_surface_speed'],
                    ironing_type=settings['ironing_type'],support_enabled=settings['enable_support'],
                    wipe_tower_xy_mm=[settings['wipe_tower_x'],settings['wipe_tower_y']],
                    limitations=['Reslice current raised-text geometry before printing; prior slice estimates are retired'])


if __name__=='__main__':
    for name in ('Control-panel-bambu.3mf','Control-panel-bambu-0.2mm.3mf'):
        result=refresh(OUT/name)
        (OUT/(name[:-4]+'-check.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False))
