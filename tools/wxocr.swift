import Foundation
import AppKit
import Vision
import CoreImage

// wxocr: Capture a screen rect and run Vision OCR.
// Usage:
//   wxocr --rect x y w h --once
//   wxocr --rect x y w h --watch fps
// Options:
//   --langs zh-Hans,en-US   (optional; default zh-Hans,en-US)
//   --scale 1.0             (optional image scale factor before OCR)

struct Args {
    var rect: CGRect = .zero
    var once: Bool = false
    var watchFPS: Double? = nil
    var langs: [String] = ["zh-Hans", "en-US"]
    var scale: Double = 1.0
    var level: String = "fast"       // fast | accurate
    var preprocess: String = "none"   // none | enhance
}

func parseArgs() -> Args? {
    var a = Args()
    var it = CommandLine.arguments.dropFirst().makeIterator()
    while let flag = it.next() {
        switch flag {
        case "--rect":
            guard let sx = it.next(), let sy = it.next(), let sw = it.next(), let sh = it.next(),
                  let x = Double(sx), let y = Double(sy), let w = Double(sw), let h = Double(sh) else { return nil }
            a.rect = CGRect(x: x, y: y, width: w, height: h)
        case "--once":
            a.once = true
        case "--watch":
            guard let s = it.next(), let fps = Double(s), fps > 0 else { return nil }
            a.watchFPS = fps
        case "--langs":
            guard let s = it.next() else { return nil }
            a.langs = s.split(separator: ",").map { String($0) }
        case "--scale":
            guard let s = it.next(), let sc = Double(s), sc > 0 else { return nil }
            a.scale = sc
        case "--level":
            guard let s = it.next() else { return nil }
            a.level = s
        case "--preprocess":
            guard let s = it.next() else { return nil }
            a.preprocess = s
        default:
            fputs("ERR: unknown arg \(flag)\n", stderr)
            return nil
        }
    }
    guard a.rect.width > 0 && a.rect.height > 0 else { return nil }
    if !a.once && a.watchFPS == nil { return nil }
    return a
}

func nowISO8601() -> String {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f.string(from: Date())
}

func captureRect(_ r: CGRect) -> CGImage? {
    // Capture on-screen content in given rect (global screen coords, origin top-left)
    return CGWindowListCreateImage(r, [.optionOnScreenOnly], kCGNullWindowID, [.bestResolution])
}

func scaleImage(_ img: CGImage, factor: Double) -> CGImage {
    guard factor != 1.0, factor > 0 else { return img }
    let w = Int(Double(img.width) * factor)
    let h = Int(Double(img.height) * factor)
    guard let colorSpace = img.colorSpace,
          let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: img.bitsPerComponent,
                              bytesPerRow: 0, space: colorSpace, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
        return img
    }
    ctx.interpolationQuality = .high
    ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
    return ctx.makeImage() ?? img
}

func preprocessImage(_ img: CGImage, mode: String) -> CGImage {
    guard mode != "none" else { return img }
    let ci = CIImage(cgImage: img)
    let context = CIContext(options: nil)
    var out = ci
    // Desaturate + increase contrast
    if let c = CIFilter(name: "CIColorControls") {
        c.setValue(out, forKey: kCIInputImageKey)
        c.setValue(0.0, forKey: kCIInputSaturationKey)
        c.setValue(1.25, forKey: kCIInputContrastKey)
        out = c.outputImage ?? out
    }
    // Sharpen luminance slightly
    if let s = CIFilter(name: "CISharpenLuminance") {
        s.setValue(out, forKey: kCIInputImageKey)
        s.setValue(0.6, forKey: kCIInputSharpnessKey)
        out = s.outputImage ?? out
    }
    if let cg = context.createCGImage(out, from: out.extent) {
        return cg
    }
    return img
}

struct OCRLine: Codable {
    let text: String
    let bbox: [Double] // [x, y, w, h] in screen pixels
    let confidence: Double
}

struct OCRFrame: Codable {
    let ts: String
    let rect: [Double] // [x, y, w, h]
    let lines: [OCRLine]
}

func recognize(img: CGImage, rect: CGRect, langs: [String], level: String) throws -> [OCRLine] {
    let request = VNRecognizeTextRequest()
    request.recognitionLanguages = langs
    request.usesLanguageCorrection = true
    request.recognitionLevel = (level == "accurate" ? .accurate : .fast)
    request.minimumTextHeight = 0.015 // filter tiny noise
    let handler = VNImageRequestHandler(cgImage: img, options: [:])
    try handler.perform([request])
    guard let results = request.results as? [VNRecognizedTextObservation] else { return [] }

    var lines: [OCRLine] = []
    for obs in results {
        guard let cand = obs.topCandidates(1).first else { continue }
        let bb = obs.boundingBox // normalized (origin bottom-left)
        let iw = Double(img.width)
        let ih = Double(img.height)
        let xImg = Double(bb.origin.x) * iw
        let yImgFromBottom = Double(bb.origin.y) * ih
        let hImg = Double(bb.size.height) * ih
        let yImgTop = Double(ih) - (yImgFromBottom + hImg)
        let wImg = Double(bb.size.width) * iw
        let x = Double(rect.origin.x) + xImg
        let y = Double(rect.origin.y) + yImgTop
        let w = wImg
        let h = hImg
        lines.append(OCRLine(text: cand.string, bbox: [x, y, w, h], confidence: Double(cand.confidence)))
    }
    return lines
}

func runOnce(rect: CGRect, langs: [String], scale: Double, level: String, preprocess: String) {
    guard let img0 = captureRect(rect) else {
        fputs("ERR: capture failed\n", stderr)
        exit(2)
    }
    let imgScaled = scaleImage(img0, factor: scale)
    let img = preprocessImage(imgScaled, mode: preprocess)
    do {
        let lines = try recognize(img: img, rect: rect, langs: langs, level: level)
        let frame = OCRFrame(ts: nowISO8601(), rect: [Double(rect.origin.x), Double(rect.origin.y), Double(rect.size.width), Double(rect.size.height)], lines: lines)
        let enc = JSONEncoder()
        if #available(macOS 10.15, *) { enc.outputFormatting = [.withoutEscapingSlashes] }
        let data = try enc.encode(frame)
        if let s = String(data: data, encoding: .utf8) { print(s) }
    } catch {
        fputs("ERR: ocr failed: \(error)\n", stderr)
        exit(3)
    }
}

func runWatch(rect: CGRect, langs: [String], scale: Double, fps: Double, level: String, preprocess: String) {
    let interval = max(0.05, 1.0 / fps)
    while true {
        autoreleasepool {
            runOnce(rect: rect, langs: langs, scale: scale, level: level, preprocess: preprocess)
        }
        fflush(stdout)
        usleep(useconds_t(interval * 1_000_000))
    }
}

guard let args = parseArgs() else {
    fputs("usage: wxocr --rect x y w h (--once | --watch fps) [--langs zh-Hans,en-US] [--scale 1.0] [--level fast|accurate] [--preprocess none|enhance]\n", stderr)
    exit(2)
}

if args.once {
    runOnce(rect: args.rect, langs: args.langs, scale: args.scale, level: args.level, preprocess: args.preprocess)
} else if let fps = args.watchFPS {
    runWatch(rect: args.rect, langs: args.langs, scale: args.scale, fps: fps, level: args.level, preprocess: args.preprocess)
}
