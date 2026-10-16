"""Pure pointer-edge decisions shared by both agents."""

from __future__ import annotations


def should_cross_out(x: float, dx: float, right: float, edge_px: float) -> bool:
    return dx > 0 and x >= right - edge_px


def should_cross_back(x: float, dx: float, left: float) -> bool:
    return dx < 0 and x <= left


def y_frac_from_quartz(quartz_y: float, origin_y: float, height: float) -> float:
    if height <= 0:
        return 0.5
    frac_from_bottom = (quartz_y - origin_y) / height
    return min(1.0, max(0.0, 1.0 - frac_from_bottom))


def quartz_y_from_frac(y_frac: float, origin_y: float, height: float) -> float:
    frac = min(1.0, max(0.0, y_frac))
    return origin_y + (1.0 - frac) * height
