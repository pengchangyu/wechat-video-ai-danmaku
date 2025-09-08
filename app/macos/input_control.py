import ctypes
import time
from typing import Tuple

# CoreGraphics constants
kCGHIDEventTap = 0
kCGMouseButtonLeft = 0
kCGEventLeftMouseDown = 1
kCGEventLeftMouseUp = 2
kCGEventMouseMoved = 5
kCGEventLeftMouseDragged = 6

kCGEventKeyDown = 10
kCGEventKeyUp = 11

# Key codes (US keyboard) for basic keys
KEYCODE_RETURN = 36
KEYCODE_V = 9

app_services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")

CGPoint = ctypes.c_double * 2


def _cg_point(x: float, y: float):
    p = CGPoint()
    p[0] = x
    p[1] = y
    return p


def move_mouse(x: float, y: float):
    app_services.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    app_services.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    app_services.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]

    event = app_services.CGEventCreateMouseEvent(None, kCGEventMouseMoved, _cg_point(x, y), kCGMouseButtonLeft)
    app_services.CGEventPost(kCGHIDEventTap, event)
    # Release
    app_services.CFRelease(event)


def click_mouse(x: float, y: float):
    app_services.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    app_services.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    app_services.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]

    down = app_services.CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, _cg_point(x, y), kCGMouseButtonLeft)
    up = app_services.CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, _cg_point(x, y), kCGMouseButtonLeft)
    app_services.CGEventPost(kCGHIDEventTap, down)
    time.sleep(0.01)
    app_services.CGEventPost(kCGHIDEventTap, up)
    app_services.CFRelease(down)
    app_services.CFRelease(up)


def key_down(keycode: int):
    app_services.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    app_services.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
    event = app_services.CGEventCreateKeyboardEvent(None, keycode, True)
    app_services.CGEventPost(kCGHIDEventTap, event)
    app_services.CFRelease(event)


def key_up(keycode: int):
    app_services.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    app_services.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
    event = app_services.CGEventCreateKeyboardEvent(None, keycode, False)
    app_services.CGEventPost(kCGHIDEventTap, event)
    app_services.CFRelease(event)


def key_tap(keycode: int, delay: float = 0.01):
    key_down(keycode)
    time.sleep(delay)
    key_up(keycode)


def paste_and_return(delay_before_return: float = 0.1):
    """Simulate Cmd+V then Return."""
    # Cmd down (mask via CGEventFlags) is more complex; instead we use AppleScript to paste reliably.
    # Fallback: send keycode V with Command down via AppleScript from main code.
    # Here we only provide Return key.
    key_tap(KEYCODE_RETURN)


def get_mouse_location() -> Tuple[float, float]:
    app_services.CGEventCreate.restype = ctypes.c_void_p
    event = app_services.CGEventCreate(None)
    app_services.CGEventGetLocation.restype = CGPoint
    loc = app_services.CGEventGetLocation(event)
    app_services.CFRelease(event)
    return float(loc[0]), float(loc[1])

