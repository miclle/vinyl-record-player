"""Separate laser-marked nameplate on the front right of the T fascia."""
from pathlib import Path

import FreeCAD as App
import Part

from fascia import dimensions as fascia_dimensions

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / 'references/fonts/sigmar-one/SigmarOne-Regular.ttf'
TEXT = 'Ariel'
V = App.Vector


def dimensions(p):
    fascia = fascia_dimensions(p)
    spec = p['fascia']['nameplate']
    width, height, thickness = (spec[key] for key in ('width', 'height', 'thickness'))
    right = fascia['x'] + fascia['length'] - spec['right_inset']
    left = right - width
    bottom = fascia['bottom'] + (p['fascia']['face_height'] - height) / 2
    front = -thickness
    if not (width > 0 and 0 < height <= p['fascia']['face_height'] and thickness > 0
            and 0 < spec['mark_depth'] < thickness
            and 0 < spec['text_height'] < height
            and spec['right_inset'] >= 0
            and left >= fascia['x'] and right <= fascia['x'] + fascia['length']):
        raise ValueError('Nameplate must fit on the fascia face')
    return dict(left=left, right=right, bottom=bottom, top=bottom + height,
                front=front, width=width, height=height, thickness=thickness)


def installation(p, doc, artwork=None):
    """Return one plate solid; the temporary Draft text is removed from the model."""
    import Draft
    if not FONT.is_file():
        raise FileNotFoundError(FONT)
    spec = p['fascia']['nameplate']
    d = dimensions(p)
    plate = Part.makeBox(d['width'], d['thickness'], d['height'],
                         V(d['left'], d['front'], d['bottom']))
    label = Draft.make_shapestring(TEXT, str(FONT), Size=spec['text_height'])
    try:
        doc.recompute()
        flat = label.Shape.copy()
        if flat.isNull() or len(flat.Faces) != len(TEXT):
            raise ValueError('Sigmar One logo did not form five letter faces')
        b = flat.BoundBox
        if b.XLength >= d['width'] or b.YLength >= d['height']:
            raise ValueError('Nameplate lettering does not fit the plate')
        if artwork is not None:
            import re
            paths = Draft.getSVG(label)
            paths = re.sub(r' stroke="[^"]*"| stroke-width="[^"]*"| style="[^"]*"', '', paths)
            artwork = Path(artwork)
            artwork.parent.mkdir(parents=True, exist_ok=True)
            x = (d['width'] - b.XLength) / 2 - b.XMin
            y = (d['height'] - b.YLength) / 2 - b.YMin
            artwork.write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{d["width"]:g}mm" height="{d["height"]:g}mm" '
                f'viewBox="0 0 {d["width"]} {d["height"]}">\n'
                f'<title>{TEXT} · Sigmar One · laser marking artwork</title>\n'
                f'<g fill="#000000" fill-rule="evenodd" transform="translate({x:.6f} {d["height"]-y:.6f}) scale(1 -1)">\n'
                f'{paths}</g>\n</svg>\n', encoding='utf-8')
        flat.rotate(V(0, 0, 0), V(1, 0, 0), 90)
        b = flat.BoundBox
        flat.translate(V(d['left'] + (d['width'] - b.XLength) / 2 - b.XMin,
                         d['front'] - b.YMin - 0.01,
                         d['bottom'] + (d['height'] - b.ZLength) / 2 - b.ZMin))
        mark = flat.extrude(V(0, spec['mark_depth'] + 0.01, 0))
        result = plate.cut(mark)
        if not result.isValid() or len(result.Solids) != 1:
            raise ValueError('Nameplate laser mark produced an invalid solid')
        return result
    finally:
        doc.removeObject(label.Name)
