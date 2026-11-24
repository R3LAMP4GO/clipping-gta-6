// Apple Vision on still frames: on-screen text (OCR) and faces, as JSON for clipper/viral.py.
// Usage: apple-vision <image> [<image> ...] -> [{"path", "text": [{"s", "area", "y"}], "faces": [{"area", "y"}]}]
// Areas are fractions of the frame; y is the box's vertical centre from the top (0-1).
import Foundation
import Vision

struct TextBox: Encodable { let s: String; let area: Double; let y: Double }
struct FaceBox: Encodable { let area: Double; let y: Double }
struct Frame: Encodable { let path: String; let text: [TextBox]; let faces: [FaceBox] }

var out: [Frame] = []
for path in CommandLine.arguments.dropFirst() {
    let handler = VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:])
    let text = VNRecognizeTextRequest()
    text.recognitionLevel = .accurate
    text.usesLanguageCorrection = true
    let faces = VNDetectFaceRectanglesRequest()
    do {  // one request per perform: both in one call failed on the Neural Engine (e5rt error 13)
        try handler.perform([text])
        try handler.perform([faces])
    } catch {
        FileHandle.standardError.write("apple-vision: \(path): \(error)\n".data(using: .utf8)!)
        out.append(Frame(path: path, text: [], faces: []))
        continue
    }
    let t = (text.results ?? []).compactMap { obs -> TextBox? in
        guard let c = obs.topCandidates(1).first else { return nil }
        let b = obs.boundingBox
        return TextBox(s: c.string, area: Double(b.width * b.height), y: Double(1 - b.midY))
    }
    let f = (faces.results ?? []).map { obs -> FaceBox in
        let b = obs.boundingBox
        return FaceBox(area: Double(b.width * b.height), y: Double(1 - b.midY))
    }
    out.append(Frame(path: path, text: t, faces: f))
}
FileHandle.standardOutput.write(try! JSONEncoder().encode(out))
