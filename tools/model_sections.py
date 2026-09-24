"""Flat-tree assembly section metadata helpers.

The saved model keeps every Part::Feature at the document root for convenient
selection.  AssemblySection preserves the former grouping semantics without
reintroducing tree containers.
"""

SECTION_PROPERTY = 'AssemblySection'
SECTION_NAMES = frozenset({
    'Cabinet',
    'Front',
    'Deck',
    'Mechanism',
    'Audio',
    'Electronics',
    'Cover',
    'Feet',
    'SelectedKit',
    'Controls',
    'FitAnalysis',
})


def _validate_section_names(sections):
    unknown = set(sections) - SECTION_NAMES
    if unknown:
        raise ValueError(f'Unknown assembly section(s): {", ".join(sorted(unknown))}')


def assign_section(obj, section):
    _validate_section_names([section])
    if not hasattr(obj, SECTION_PROPERTY):
        obj.addProperty('App::PropertyString', SECTION_PROPERTY, 'Organization')
    setattr(obj, SECTION_PROPERTY, section)
    obj.setEditorMode(SECTION_PROPERTY, 1)
    return obj


def section_objects(doc, *sections):
    _validate_section_names(sections)
    wanted = set(sections)
    return [obj for obj in doc.Objects
            if obj.TypeId == 'Part::Feature'
            and getattr(obj, SECTION_PROPERTY, '') in wanted]
