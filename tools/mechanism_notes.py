"""Shared parameter-derived wording for mechanism drawings (no CAD runtime)."""


def spring_positions_note(cfg):
    hours = '/'.join(f'{hour:g}' for hour in cfg['spring_clock_hours'])
    return f"R{cfg['spring_radius']:g}，约{hours}点"
