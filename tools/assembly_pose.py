"""Persist a viewing angle while keeping a reproducible closed assembly datum."""
from hinges import moving_names, rotation


def initialize(doc):
    state = doc.addObject('App::FeaturePython', 'AssemblyState')
    state.Label = '展示姿态 · 开盖角度'
    state.addProperty('App::PropertyAngle', 'CoverAngle', 'Display').CoverAngle = 0
    state.setEditorMode('CoverAngle', 1)
    for name in moving_names():
        obj = doc.getObject(name)
        obj.addProperty('App::PropertyPlacement', 'ClosedPlacement', 'Display')
        obj.ClosedPlacement = obj.Placement
        obj.setEditorMode('ClosedPlacement', 1)


def set_cover_angle(doc, parameters, angle):
    """Move the lid, moving leaves, spacers and backing plates together."""
    if not 0 <= angle <= parameters['cover_angle_open']:
        raise ValueError('Cover angle must be between 0 and the sampled opening angle')
    transform = rotation(parameters, angle)
    for name in moving_names():
        obj = doc.getObject(name)
        obj.Placement = transform.multiply(obj.ClosedPlacement)
    doc.AssemblyState.CoverAngle = angle
    doc.recompute()
