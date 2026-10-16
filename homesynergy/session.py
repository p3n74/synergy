"""Remote pointer position on the Windows virtual desktop. No OS calls."""

from __future__ import annotations


class RemotePointer:
    def __init__(self, left: int, top: int, width: int, height: int) -> None:
        self.left = int(left)
        self.top = int(top)
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.x = float(self.left)
        self.y = float(self.top)
        self.active = False

    def on_enter(self, y_frac: float) -> tuple[str, int, int]:
        frac = min(1.0, max(0.0, float(y_frac)))
        self.active = True
        self.x = self.left + 8
        self.y = self.top + frac * (self.height - 1)
        return ("move", int(self.x), int(self.y))

    def on_mouse(self, dx: float, dy: float) -> list[tuple]:
        if not self.active:
            return []
        self.x += dx
        self.y += dy
        if should_leave(self.x, dx, self.left):
            frac = (self.y - self.top) / float(self.height)
            self.active = False
            self.x = float(self.left)
            return [("leave", min(1.0, max(0.0, frac)))]
        self._clamp()
        return [("move", int(self.x), int(self.y))]

    def on_leave(self) -> None:
        self.active = False

    def _clamp(self) -> None:
        max_x = self.left + self.width - 1
        max_y = self.top + self.height - 1
        self.x = min(max(self.x, self.left), max_x)
        self.y = min(max(self.y, self.top), max_y)


def should_leave(x: float, dx: float, left: float) -> bool:
    return dx < 0 and x < left
