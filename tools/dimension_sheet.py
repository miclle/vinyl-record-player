"""Orthographic linework projected directly from CAD with TechDraw."""
import base64
import json
import re
from datetime import date
from html import escape
from pathlib import Path
import FreeCAD as App
import Part
import TechDraw

ROOT=Path(__file__).resolve().parents[1]


def create(doc,p):
    def projection(names,direction,rotation):
        objs=[]
        for name in names:objs.extend(doc.getObject(name).Group)
        svg=TechDraw.projectToSVG(Part.makeCompound([o.Shape for o in objs]),App.Vector(*direction))
        svg=re.sub(r'\bid\s*=\s*"[^"]*"','',svg).replace('stroke-width="1.0"','stroke-width="0.35"')
        return '<g transform="rotate(%s)">%s</g>'%(rotation,svg)
    external=['Cabinet','Front','Deck','Mechanism','Cover','Feet']
    front=projection(external,(0,-1,0),90)
    right=projection(external,(1,0,0),-90)
    top=projection(['Cabinet','Front','Deck','Mechanism'],(0,0,1),0)
    png=base64.b64encode((ROOT/'previews/open.png').read_bytes()).decode()
    W,D,H=p['width'],p['depth'],p['closed_height'];s=1.15
    out=['''<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1030" viewBox="0 0 1400 1030">
<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto-start-reverse"><path d="M0,1 L7,4 L0,7" fill="none" stroke="#8a5137"/></marker></defs>
<rect width="1400" height="1030" fill="white"/>
<style>text{font-family:'PingFang SC','Noto Sans CJK SC',sans-serif;fill:#252a2d}.title{font-size:27px;font-weight:600}.label{font-size:18px;font-weight:600}.note{font-size:16px}.dim{stroke:#8a5137;stroke-width:1;fill:none}.ext{stroke:#aba49e;stroke-width:0.8}.value{font-size:16px;fill:#8a5137}</style>
<text x="60" y="49" class="title">LUMI 参考外形 · 一低音两全频概念 CAD</text>
<line x1="60" y1="68" x2="1340" y2="68" stroke="#d8d3cc"/>
<text x="80" y="99" class="label">俯视 · 移除防尘盖</text>
<text x="80" y="595" class="label">正视 · 闭盖</text>
<text x="800" y="595" class="label">右视 · 闭盖</text>''']
    out.append(f'<text x="1340" y="48" text-anchor="end" class="note">{escape(p["revision"])} / {date.today().isoformat()} / 单位 mm</text>')
    out.append(f'<g transform="translate(80 510) scale({s})">{top}</g>')
    out.append(f'<g transform="translate(80 865) scale({s})">{front}</g>')
    out.append(f'<g transform="translate(800 865) scale({s})">{right}</g>')
    out.append(f'<image x="710" y="76" width="615" height="440" href="data:image/png;base64,{png}"/>')
    def hdim(x,y,width,from_y,label):
        out.append(f'<path class="ext" d="M{x},{from_y} V{y+6} M{x+width},{from_y} V{y+6}"/>')
        out.append(f'<path class="dim" marker-start="url(#arrow)" marker-end="url(#arrow)" d="M{x},{y} H{x+width}"/><text class="value" x="{x+width/2}" y="{y-9}" text-anchor="middle">{label}</text>')
    def vdim(x,y,height,from_x,label):
        out.append(f'<path class="ext" d="M{from_x},{y} H{x+6} M{from_x},{y+height} H{x+6}"/>')
        out.append(f'<path class="dim" marker-start="url(#arrow)" marker-end="url(#arrow)" d="M{x},{y} V{y+height}"/><text class="value" transform="translate({x+23},{y+height/2}) rotate(-90)" text-anchor="middle">{label}</text>')
    hdim(80,552,W*s,510,f'{W:.1f}')
    hdim(80,912,W*s,865,f'{W:.1f}')
    hdim(800,912,D*s,865,f'{D:.1f}')
    vdim(635,510-D*s,D*s,80+W*s,f'{D:.1f}')
    vdim(1245,865-H*s,H*s,800+D*s,f'{H:.1f} *')
    # The platter diameter is tied to its projected geometric boundary.
    diameter=p['platter_diameter']
    hdim(80+(p['platter_x']-diameter/2)*s,510-p['platter_y']*s,diameter*s,510-p['platter_y']*s,f'Ø{diameter:g}')
    out.extend([f'<text x="750" y="532" class="note">轴距 {p["pivot_distance"]:g} · 有效臂长 {p["arm_effective_length"]:g} · 一低音两全频占位</text>',
                f'<text x="750" y="558" class="note">前格栅后倾 {90-p["front_angle"]:g}° · 木壳厚 {p["wall"]:g}（估算）</text>',
                '<line x1="60" y1="948" x2="1340" y2="948" stroke="#d8d3cc"/>',
                f'<text x="60" y="978" class="note">* {H:g} 为当前闭盖总高；原图未明确测量基准。板厚、盖高及内部接口为本项目估算。</text>',
                f'<text x="60" y="1006" class="note">线稿为机壳基准；深 {D:g} 不含 AC 法兰，含法兰 {D+p["ac_inlet"]["flange_thickness"]:g}。外观 / 空间评审用，非生产加工图。</text>','</svg>'])
    path=ROOT/'previews/dimensions.svg'
    path.write_text('\n'.join(out))
    from PySide import QtSvg,QtGui,QtCore
    renderer=QtSvg.QSvgRenderer(str(path))
    canvas=QtGui.QImage(1400,1030,QtGui.QImage.Format_ARGB32)
    canvas.fill(QtCore.Qt.white)
    painter=QtGui.QPainter(canvas);renderer.render(painter);painter.end()
    canvas.save(str(ROOT/'previews/dimensions.png'))
    return path
