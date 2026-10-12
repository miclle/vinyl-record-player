"""Finished five-sided cover dimensions, independent of the wooden box width."""
import math


def dimensions(p):
    width, depth, height, wall = (p[k] for k in
        ('cover_width', 'cover_depth', 'cover_height', 'cover_wall'))
    if not all(math.isfinite(v) and v > 0 for v in (width, depth, height, wall)):
        raise ValueError('Dust cover dimensions must be finite and positive')
    if min(width, depth) <= 2*wall or height <= wall:
        raise ValueError('Dust cover wall leaves no usable cavity')
    if abs(p['cover_bottom']-p['cabinet_top']) > 1e-6:
        raise ValueError('Dust cover must land on the cabinet top')
    if abs(p['closed_height']-p['cover_bottom']-height) > 1e-6:
        raise ValueError('Closed height must include the finished dust cover height')
    left, front = (p['width']-width)/2, (p['depth']-depth)/2
    return dict(width=width, depth=depth, height=height, wall=wall,
                left=left, front=front, rear=front+depth,
                bottom=p['cover_bottom'], top=p['closed_height'],
                inner_width=width-2*wall, inner_depth=depth-2*wall,
                inner_height=height-wall)
