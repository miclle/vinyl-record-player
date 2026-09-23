"""Actual FreeCAD viewport renders; no generated/product photo composites."""
from pathlib import Path
import FreeCAD as App
import FreeCADGui as Gui
import Part
from hinges import moving_names, rotation as hinge_rotation

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
    originals={name:doc.getObject(name).Placement for name in moving_names()}
    for name,original in originals.items():
        doc.getObject(name).Placement=hinge_rotation(p,p['cover_angle_open']).multiply(original)
    doc.recompute();iso();save('open.png')
    for name,original in originals.items():doc.getObject(name).Placement=original
    doc.recompute()
    view.setCameraOrientation(App.Rotation(App.Vector(1,0,0),90).Q);view.fitAll();save('front.png')
    view.setCameraOrientation(App.Rotation(App.Vector(0,1,0),App.Vector(0,0,1),App.Vector(1,0,0),'ZXY').Q);view.fitAll();save('right.png')
    view.viewRear();view.fitAll();save('rear.png')
    doc.getObject('ACInlet').ViewObject.Visibility=False
    save('rear-cutouts.png')
    doc.getObject('ACInlet').ViewObject.Visibility=True
    view.setCameraOrientation(App.Rotation(App.Vector(1,0,0),180).Q);view.fitAll();save('bottom.png')
    # Top view intentionally omits the cover to show mechanical layout.
    for obj in groups['Cover'].Group:obj.ViewObject.Visibility=False
    view.setCameraOrientation(App.Rotation().Q);view.fitAll();save('top.png')
    visible={obj.Name:obj.ViewObject.Visibility for obj in doc.Objects if obj.TypeId=='Part::Feature'}
    for key in ['Front','Mechanism','Deck']:
        for obj in groups[key].Group:obj.ViewObject.Visibility=False
    for name in ['AcousticRoof','Baffle','BearingPocket']:
        doc.getObject(name).ViewObject.Visibility=False
    floor=doc.getObject('Bottom')
    floor_color=floor.ViewObject.ShapeColor
    floor.ViewObject.ShapeColor=(0.82,0.80,0.76)
    iso();save('internal.png')
    view.viewTop();view.fitAll();save('audio-layout.png')
    floor.ViewObject.ShapeColor=floor_color
    for name,value in visible.items():doc.getObject(name).ViewObject.Visibility=value
    for obj in groups['Cover'].Group:obj.ViewObject.Visibility=True
    iso()
    doc.recompute()
    doc.save()
    render_foot_detail(doc)
    render_hinge_detail(doc,p)
    (ROOT/'cad/render.done').write_text('Rendered closed, open, front, right, bottom, top, rear, internal, audio-layout from FreeCAD viewport.\n')


def render_foot_detail(source):
    """Temporary quarter section; never cut or save the source assembly."""
    import json
    p=json.loads(source.GeometryDatums.BuildParametersJSON)
    x,y=p['feet']['side_inset'],p['feet']['front_y']
    crop=Part.makeBox(54,60,60,App.Vector(x-21,y-30,0))
    cut=Part.makeBox(40,30,60,App.Vector(x,y-30,0))
    detail=App.newDocument('FootInstallationDetail')
    try:
        for name,color in [('Bottom',(0.63,0.43,0.26)),('Foot0',(0.06,0.07,0.08)),
                           ('FootMount0',(0.45,0.48,0.51))]:
            obj=detail.addObject('Part::Feature',name+'Section')
            obj.Shape=source.getObject(name).Shape.common(crop).cut(cut)
            obj.ViewObject.ShapeColor=color
            obj.ViewObject.DisplayMode='Flat Lines'
            if name=='Foot0':
                obj.ViewObject.DiffuseColor=[(0.73,0.75,0.77) if face.CenterOfMass.z>=p['feet']['rubber_height'] else color
                                            for face in obj.Shape.Faces]
        detail.recompute()
        view=Gui.getDocument(detail.Name).activeView()
        # Export immediately, without an animated camera transition in progress.
        view.stopAnimating()
        view.setAnimationEnabled(False)
        view.setCameraType('Orthographic')
        view.setCameraOrientation(App.Rotation(App.Vector(1,1,0),App.Vector(-1,1,2),App.Vector(1,-1,1),'ZXY').Q)
        view.fitAll();Gui.updateGui()
        view.saveImage(str(ROOT/'previews/feet-installation.png'),1600,1200,'White')
    finally:
        App.closeDocument(detail.Name)
        App.setActiveDocument(source.Name)


def render_hinge_detail(source,p):
    """Read-only close-up of both mounting faces; source placements are untouched."""
    detail=App.newDocument('HingeInstallationDetail')
    try:
        x=p['hinges']['center_x'][0]
        crop=Part.makeBox(75,45,85,App.Vector(x-37.5,p['depth']-25,p['cabinet_top']-40))
        for name in ['Back','DustCover','HingeBase0','HingePin0','HingeSpacer0','HingeBacking0']:
            original=source.getObject(name)
            obj=detail.addObject('Part::Feature',name)
            obj.Shape=original.Shape.common(crop)
            obj.ViewObject.ShapeColor=original.ViewObject.ShapeColor
            obj.ViewObject.DisplayMode='Flat Lines'
            obj.ViewObject.Transparency=65 if name=='DustCover' else 0
        detail.recompute()
        view=Gui.getDocument(detail.Name).activeView()
        view.setAnimationEnabled(False)
        view.setCameraType('Orthographic')
        view.setCameraOrientation(App.Rotation(App.Vector(1,-1,0),App.Vector(1,1,2),App.Vector(-1,1,1),'ZXY').Q)
        view.fitAll();Gui.updateGui()
        view.saveImage(str(ROOT/'previews/hinge-installation.png'),1400,1200,'White')
    finally:
        App.closeDocument(detail.Name)
        App.setActiveDocument(source.Name)
