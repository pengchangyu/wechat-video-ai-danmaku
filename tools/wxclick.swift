import Foundation
import AppKit

// Usage: wxclick <x_topLeft_pixels> <y_topLeft_pixels>
// - Coordinates captured from a top-left origin (like Tk's pointer), in device pixels.
// - CoreGraphics CGEvent expects global display coordinates with top-left origin on modern macOS,
//   so we DO NOT flip Y here. We only post the given coordinates directly.

func err(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(2)
}

guard CommandLine.arguments.count == 3,
      let xTopLeftPx = Double(CommandLine.arguments[1]),
      let yTopLeftPx = Double(CommandLine.arguments[2]) else {
    err("usage: wxclick <x_topLeft_points> <y_topLeft_points>")
}

// Use coordinates as-is (top-left origin, pixels)
let xPx = xTopLeftPx
let yPx = yTopLeftPx

let loc = CGPoint(x: xPx, y: yPx)

func click(at p: CGPoint) -> Bool {
    guard let down = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: p, mouseButton: .left),
          let up = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: p, mouseButton: .left) else {
        return false
    }
    down.post(tap: .cghidEventTap)
    // small delay to emulate real click
    usleep(15_000)
    up.post(tap: .cghidEventTap)
    return true
}

// Move cursor to target to reduce miss on some apps
if let move = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: loc, mouseButton: .left) {
    move.post(tap: .cghidEventTap)
    usleep(10_000)
}

if click(at: loc) {
    exit(0)
} else {
    err("click failed")
}
