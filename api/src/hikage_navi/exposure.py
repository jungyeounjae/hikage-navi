from collections.abc import Sequence

from hikage_navi.constants import WALK_M_PER_MIN


def max_run_sun_m(shaded: Sequence[bool], steps: Sequence[float]) -> float:
    best = 0.0
    cur = 0.0
    for is_shade, step in zip(shaded, steps):
        if is_shade:
            cur = 0.0
        else:
            cur += float(step)
            if cur > best:
                best = cur
    return best


def sun_seconds(distance_m: float) -> int:
    return int(round(float(distance_m) / WALK_M_PER_MIN * 60.0))
