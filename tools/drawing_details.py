"""Read-only panel drilling sheets and a clipped assembly section from saved CAD."""
import math

import FreeCAD as App
import Part
from feet import positions as foot_positions

V = App.Vector


def panel_details(doc, p, project_shape, project=True):
    sheets = []
    zlo = p['foot_height'] + p['wall']
    sine = math.sin(math.radians(p['front_angle']))
    specs = [
        ('Bottom', 1, 'A-H01', '底板 / 通孔与底面盲预孔', 'bottom', ('X', 'Y')),
        ('Back', 1, 'A-H02', '后板 / 倒相孔、沉台与 AC 开孔', 'front', ('X', 'Z')),
        ('Baffle', 2, 'B-H01', '倾斜扬声器障板 / 前表面法向开孔', 'baffle_face', ('X', 'S')),
        ('AcousticRoof', 2, 'B-H02', '音腔顶板 / 轴承避让孔', 'top', ('X', 'Y')),
        ('FloatingDeck', 2, 'B-H03', '浮动底板 / 主轴孔', 'top', ('X', 'Y')),
    ]
    for key, volume, code, title, view, axes in specs:
        shape = doc.getObject(key).Shape
        b = shape.optimalBoundingBox(False)
        holes = []
        notes = []

        def round_hole(identifier, x, y, diameter, kind='through', depth=None):
            h = dict(id=identifier, u_mm=x, v_mm=y, diameter_mm=diameter, kind=kind)
            if depth is not None:
                h['depth_mm'] = depth
            holes.append(h)
            return h

        if key == 'Bottom':
            w = p['woofer']; fs = p['feet']
            round_hole('H1', w['center_x']-b.XMin, w['center_y']-b.YMin, w['cutout_diameter'])
            for i, (x, y) in enumerate(foot_positions(p), 1):
                round_hole(f'F{i}', x-b.XMin, y-b.YMin, fs['panel_hole_diameter_assumption'])
            for i, (x, y) in enumerate(foot_positions(p), 1):
                for j, angle in enumerate((0, 120, 240), 1):
                    r = fs['mount_pitch_circle_assumption']/2
                    round_hole(f'P{i}.{j}', x-b.XMin+r*math.cos(math.radians(angle)),
                               y-b.YMin+r*math.sin(math.radians(angle)),
                               fs['pilot_diameter_assumption'], 'blind', fs['pilot_depth_assumption'])
            notes = [
                '从桌面向上看底面；图左上角 O 对应板件左前角。+X 向右，+Y 向下；孔表 Y 从前边量取。',
                f"H1：低音通孔（暂定）。F1-F4：脚座通孔；P 为底面盲预孔，深 {fs['pilot_depth_assumption']:g}，剩余木厚 {b.ZLength-fs['pilot_depth_assumption']:g}。",
                f"每组 P 绕同号 F 分布于 Ø{fs['mount_pitch_circle_assumption']:g} 圆上，角度从 +X 朝 +Y 为 0°/120°/240°；脚座孔均为安装假设。",
                '功放、变压器及其他固定螺孔尚未建模，须实物确认后另行定位；不能按本图推定这些孔位。',
            ]
            size = [b.XLength, b.YLength]
        elif key == 'Back':
            port = p['bass_port']; inlet = p['ac_inlet']
            h = round_hole('H1', port['center_x']-b.XMin, port['center_z']-b.ZMin,
                           port['inner_diameter']+2*port['wall_thickness'])
            h['recess'] = dict(diameter_mm=port['flange_diameter'], depth_mm=port['flange_thickness'], face='后侧')
            holes.append(dict(id='H2', kind='rounded_rectangle', u_mm=inlet['center_x']-b.XMin,
                              v_mm=inlet['center_z']-b.ZMin, width_mm=inlet['cutout_width'],
                              height_mm=inlet['cutout_height'], radius_mm=inlet['cutout_radius']))
            for i, sign in enumerate((-1, 1), 3):
                round_hole(f'H{i}', inlet['center_x']-b.XMin,
                           inlet['center_z']+sign*inlet['mount_hole_pitch']/2-b.ZMin,
                           inlet['mount_hole_diameter'])
            notes = [
                '主图从箱内向后看（+X 向右）；O 为后板左下角。后侧沉台以虚线叠画，保持与正面相同坐标，勿镜像孔位。',
                f"H1 同心沉台：从箱外后侧加工 Ø{port['flange_diameter']:g}，深 {port['flange_thickness']:g}；通孔与沉台轴心相同。",
                f"H2 横向圆角通孔；H3/H4 上下孔距 {inlet['mount_hole_pitch']:g}。H2 左下角 = ({inlet['center_x']-b.XMin-inlet['cutout_width']/2:g}, {inlet['center_z']-b.ZMin-inlet['cutout_height']/2:g})。",
                'AC 开孔须先实物试孔；面板紧固、螺钉长度及电气安装未确认。接口板、铰链等未建模安装孔仍待确认。',
            ]
            size = [b.XLength, b.ZLength]
        elif key == 'Baffle':
            # Only the actual front face: projecting the entire thickness would
            # enlarge the S envelope by the bevel's offset and shift the datum.
            normal = V(0, -sine, math.cos(math.radians(p['front_angle'])))
            faces = [f for f in shape.Faces if isinstance(f.Surface, Part.Plane)
                     and f.normalAt(0, 0).dot(normal) > 0.999999]
            face = max(faces, key=lambda f: f.Area).copy()
            face.rotate(V(0, 0, 0), V(1, 0, 0), 90-p['front_angle'])
            shape = face
            for i, x in enumerate(p['fullrange']['center_x'], 1):
                round_hole(f'H{i}', x-b.XMin, (p['fullrange']['center_z']-zlo)/sine,
                           p['fullrange']['cutout_diameter'])
            size = [b.XLength, (p['acoustic']['roof_bottom_z']-zlo)/sine]
            notes = [
                '主图垂直于障板前表面；O 为成形后前表面左下角，S 沿斜面向上量取，图中孔为真实圆。',
                f"孔中心投影竖高为 {p['fullrange']['center_z']-zlo:g}，沿斜面 S={holes[0]['v_mm']:.3f}；请按 S 划线。孔轴垂直板面，法向厚 {p['acoustic']['baffle_thickness']:g}。",
                f"安装后倾 {90-p['front_angle']:g}°；上下斜口成形后前表面长 {size[1]:.3f}。局部装配剖视见第 01 册 A-03；三视及备料见 B-P01。",
                '扬声器固定螺孔、板件连接孔未知；本页只标已有声孔，不作为完整安装放行。',
            ]
        else:
            diameter = 28 if key == 'AcousticRoof' else 20.4
            round_hole('H1', p['platter_x']-b.XMin, p['platter_y']-b.YMin, diameter)
            size = [b.XLength, b.YLength]
            notes = [
                '俯视；O 为板件左前角，+X 向右，+Y 向后（图上方）；所有孔位均相对该板成形边。',
                '圆孔沿 Z 贯通，孔表坐标以孔轴心为准。',
                ('此孔与通用轴承密封避让杯配合，保留在当前模型中；选定弯臂机芯安装时须重新核对。'
                 if key == 'AcousticRoof' else '主轴孔为通用机芯暂定值；选定机芯固定孔、轮廓开口及弹性支承固定方式尚未设计。'),
                '板件连接螺孔未定义；未标孔位不得按示意位置直接开孔。',
            ]
        projection = project_shape(shape, 'front' if view == 'baffle_face' else view) if project else {}
        sheets.append(dict(key=key, code=code, title=title, volume=volume, view=view, axes=axes,
                           size_mm=size, projection=projection, holes=holes, notes=notes,
                           thickness_mm=p['acoustic']['baffle_thickness'] if key == 'Baffle' else
                           (b.YLength if key == 'Back' else b.ZLength)))
    return sheets


def baffle_section(doc, p, project_shape, project=True):
    x = p['width']/2
    clip = Part.makeBox(2, 90, p['cabinet_top']+1, V(x-1, 0, 0))
    names = ['Bottom', 'Baffle', 'AcousticRoof', 'GrilleCloth', 'LowerRail', 'Fascia',
             'LightChannel', 'LightDiffuser'] + [f'Slat{i:02}' for i in range(1, p['slat_count']+1)]
    parts = []
    for name in names:
        clipped = doc.getObject(name).Shape.common(clip)
        section = Part.makeCompound(clipped.slice(V(1, 0, 0), x))
        if section.isNull() or not section.Edges:
            continue
        b = section.optimalBoundingBox(False)
        parts.append(dict(key=name, origin_mm=[b.YMin, b.ZMin], size_mm=[b.YLength, b.ZLength],
                          projection=project_shape(section, 'right') if project else {}))
    return dict(x_mm=x, y_limit_mm=90, parts=parts)
