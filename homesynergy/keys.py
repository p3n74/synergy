"""Mac virtual keycodes to Windows virtual keys. US keyboard layout."""

from __future__ import annotations

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_CAPITAL = 0x14
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_PRIOR = 0x21
VK_NEXT = 0x22
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_DELETE = 0x2E
VK_LWIN = 0x5B
VK_NUMPAD0 = 0x60
VK_MULTIPLY = 0x6A
VK_ADD = 0x6B
VK_SUBTRACT = 0x6D
VK_DECIMAL = 0x6E
VK_DIVIDE = 0x6F
VK_F1 = 0x70
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_OEM_1 = 0xBA
VK_OEM_PLUS = 0xBB
VK_OEM_COMMA = 0xBC
VK_OEM_MINUS = 0xBD
VK_OEM_PERIOD = 0xBE
VK_OEM_2 = 0xBF
VK_OEM_3 = 0xC0
VK_OEM_4 = 0xDB
VK_OEM_5 = 0xDC
VK_OEM_6 = 0xDD
VK_OEM_7 = 0xDE

# ANSI Mac keycodes -> Windows VK for non-modifiers.
_MAC_TO_VK: dict[int, int] = {
    0: ord("A"),
    1: ord("S"),
    2: ord("D"),
    3: ord("F"),
    4: ord("H"),
    5: ord("G"),
    6: ord("Z"),
    7: ord("X"),
    8: ord("C"),
    9: ord("V"),
    11: ord("B"),
    12: ord("Q"),
    13: ord("W"),
    14: ord("E"),
    15: ord("R"),
    16: ord("Y"),
    17: ord("T"),
    18: ord("1"),
    19: ord("2"),
    20: ord("3"),
    21: ord("4"),
    22: ord("6"),
    23: ord("5"),
    24: VK_OEM_PLUS,
    25: ord("9"),
    26: ord("7"),
    27: VK_OEM_MINUS,
    28: ord("8"),
    29: ord("0"),
    30: VK_OEM_6,
    31: ord("O"),
    32: ord("U"),
    33: VK_OEM_4,
    34: ord("I"),
    35: ord("P"),
    36: VK_RETURN,
    37: ord("L"),
    38: ord("J"),
    39: VK_OEM_7,
    40: ord("K"),
    41: VK_OEM_1,
    42: VK_OEM_5,
    43: VK_OEM_COMMA,
    44: VK_OEM_2,
    45: ord("N"),
    46: ord("M"),
    47: VK_OEM_PERIOD,
    48: VK_TAB,
    49: VK_SPACE,
    50: VK_OEM_3,
    51: VK_BACK,
    53: VK_ESCAPE,
    65: VK_DECIMAL,
    67: VK_MULTIPLY,
    69: VK_ADD,
    71: VK_DECIMAL,  # keypad clear, close enough
    75: VK_DIVIDE,
    76: VK_RETURN,
    78: VK_SUBTRACT,
    82: VK_NUMPAD0,
    83: VK_NUMPAD0 + 1,
    84: VK_NUMPAD0 + 2,
    85: VK_NUMPAD0 + 3,
    86: VK_NUMPAD0 + 4,
    87: VK_NUMPAD0 + 5,
    88: VK_NUMPAD0 + 6,
    89: VK_NUMPAD0 + 7,
    91: VK_NUMPAD0 + 8,
    92: VK_NUMPAD0 + 9,
    96: VK_F1 + 4,
    97: VK_F1 + 5,
    98: VK_F1 + 6,
    99: VK_F1 + 2,
    100: VK_F1 + 7,
    101: VK_F1 + 8,
    103: VK_F1 + 10,
    109: VK_F1 + 9,
    111: VK_F1 + 11,
    114: 0x2D,  # help key -> insert
    115: VK_HOME,
    116: VK_PRIOR,
    117: VK_DELETE,
    118: VK_F1 + 3,
    119: VK_END,
    120: VK_F1 + 1,
    121: VK_NEXT,
    122: VK_F1,
    123: VK_LEFT,
    124: VK_RIGHT,
    125: VK_DOWN,
    126: VK_UP,
}

# Mac modifier keycodes.
MOD_LEFT_SHIFT = 56
MOD_RIGHT_SHIFT = 60
MOD_LEFT_CTRL = 59
MOD_RIGHT_CTRL = 62
MOD_LEFT_OPTION = 58
MOD_RIGHT_OPTION = 61
MOD_LEFT_CMD = 55
MOD_RIGHT_CMD = 54
MOD_CAPS = 57

_MODIFIERS = {
    MOD_LEFT_SHIFT,
    MOD_RIGHT_SHIFT,
    MOD_LEFT_CTRL,
    MOD_RIGHT_CTRL,
    MOD_LEFT_OPTION,
    MOD_RIGHT_OPTION,
    MOD_LEFT_CMD,
    MOD_RIGHT_CMD,
    MOD_CAPS,
}

EXTENDED_VKS = {
    VK_LEFT,
    VK_UP,
    VK_RIGHT,
    VK_DOWN,
    VK_PRIOR,
    VK_NEXT,
    VK_END,
    VK_HOME,
    VK_DELETE,
    0x2D,
    VK_RCONTROL,
    VK_RMENU,
    VK_LWIN,
    VK_DIVIDE,
}


def is_modifier(mac_keycode: int) -> bool:
    return mac_keycode in _MODIFIERS


def mac_to_vk(mac_keycode: int, command_is_control: bool = True) -> int | None:
    if mac_keycode == MOD_LEFT_SHIFT:
        return VK_LSHIFT
    if mac_keycode == MOD_RIGHT_SHIFT:
        return VK_RSHIFT
    if mac_keycode == MOD_LEFT_CTRL:
        return VK_LCONTROL
    if mac_keycode == MOD_RIGHT_CTRL:
        return VK_RCONTROL
    if mac_keycode == MOD_LEFT_OPTION:
        return VK_LMENU
    if mac_keycode == MOD_RIGHT_OPTION:
        return VK_RMENU
    if mac_keycode in (MOD_LEFT_CMD, MOD_RIGHT_CMD):
        return VK_LCONTROL if command_is_control else VK_LWIN
    if mac_keycode == MOD_CAPS:
        return VK_CAPITAL
    return _MAC_TO_VK.get(mac_keycode)
