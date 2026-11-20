// Apple's on-device speech model (SpeechAnalyzer + SpeechTranscriber, macOS 26+): prints {"words": [{"w","s","e"}]}
// for one audio file, the same word format as clipper/transcribe.py. Usage: apple-asr <audio> [locale]
import AVFoundation
import Foundation
import Speech

struct Word: Encodable { let w: String; let s: Double; let e: Double }
struct Out: Encodable { let words: [Word] }

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(1)
}

let args = CommandLine.arguments
guard args.count >= 2 else { fail("usage: apple-asr <audio> [locale]") }
let url = URL(fileURLWithPath: args[1])
let locale = Locale(identifier: args.count > 2 ? args[2] : "en-US")

do {
    guard let supported = await SpeechTranscriber.supportedLocale(equivalentTo: locale) else {
        fail("apple-asr: no on-device model for \(locale.identifier)")
    }
    let transcriber = SpeechTranscriber(locale: supported, transcriptionOptions: [], reportingOptions: [],
                                        attributeOptions: [.audioTimeRange])
    if let install = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
        try await install.downloadAndInstall()  // one-time model download, then it runs offline
    }
    let analyzer = SpeechAnalyzer(modules: [transcriber])
    let file = try AVAudioFile(forReading: url)
    let collect = Task { () -> [Word] in
        var words: [Word] = []
        for try await result in transcriber.results where result.isFinal {
            for run in result.text.runs {
                guard let range = run.audioTimeRange else { continue }
                let text = String(result.text[run.range].characters).trimmingCharacters(in: .whitespacesAndNewlines)
                let parts = text.split(whereSeparator: { $0.isWhitespace }).map(String.init)
                guard !parts.isEmpty else { continue }
                // a run is usually one word; split the rare multi-word run evenly over its time range
                let s = range.start.seconds, step = (range.end.seconds - s) / Double(parts.count)
                for (i, p) in parts.enumerated() {
                    words.append(Word(w: p, s: s + step * Double(i), e: s + step * Double(i + 1)))
                }
            }
        }
        return words
    }
    if let last = try await analyzer.analyzeSequence(from: file) {
        try await analyzer.finalizeAndFinish(through: last)
    } else {
        await analyzer.cancelAndFinishNow()
    }
    let words = try await collect.value
    let data = try JSONEncoder().encode(Out(words: words))
    FileHandle.standardOutput.write(data)
} catch {
    fail("apple-asr: \(error)")
}
