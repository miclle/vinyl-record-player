"""Actual FreeCAD viewport renders; no generated/product photo composites."""
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui

ROOT=Path(__file__).resolve().parents[1]


def render(doc,p,groups):
    view=Gui.activeDocument().activeView()
    view.stopAnimating()
    view.setAnimationEnabled(False)
    view.setCameraType('Orthographic')
    rotation=App.Rotation(App.Vector(1,1,0),App.Vector(-1,1,2),App.Vector(1,-1,1),'ZXY')
    def iso():
        view.setCameraOrientation(rotation.Q)
        view.fitAll()
        Gui.updateGui()
    def save(name):
        Gui.updateGui()
        view.saveImage(str(ROOT/'previews'/name),1600,1200,'White')
    iso(); save('closed.png')
    lid=doc.getObject('DustCover')
    original=lid.Placement
    hinge=doc.getObject('GeometryDatums').CoverHinge
    lid.Placement=App.Placement(App.Vector(),App.Rotation(App.Vector(1,0,0),-p['cover_angle_open']),hinge)
    doc.recompute();iso();save('open.png')
    lid.Placement=original
    doc.recompute()
    view.setCameraOrientation(App.Rotation(App.Vector(1,0,0),90).Q);view.fitAll();save('front.png')
    view.setCameraOrientation(App.Rotation(App.Vector(0,1,0),App.Vector(0,0,1),App.Vector(1,0,0),'ZXY').Q);view.fitAll();save('right.png')
    view.setCameraOrientation(App.Rotation(App.Vector(1,0,0),180).Q);view.fitAll();save('bottom.png')
    # Top view intentionally omits the cover to show mechanical layout.
    for obj in groups['Cover'].Group:obj.ViewObject.Visibility=False
    view.setCameraOrientation(App.Rotation().Q);view.fitAll();save('top.png')
    visible={obj.Name:obj.ViewObject.Visibility for obj in doc.Objects if obj.TypeId=='Part::Feature'}
    for key in ['Front','Mechanism','Deck']:
        for obj in groups[key].Group:obj.ViewObject.Visibility=False
    for name in ['AcousticRoof','Baffle']:
        doc.getObject(name).ViewObject.Visibility=False
    iso();save('internal.png')
    for name,value in visible.items():doc.getObject(name).ViewObject.Visibility=value
    for obj in groups['Cover'].Group:obj.ViewObject.Visibility=True
    iso()
    doc.recompute()
    doc.save()
    (ROOT/'cad/render.done').write_text('Rendered closed, open, front, right, bottom, top, internal from FreeCAD viewport.\n')
