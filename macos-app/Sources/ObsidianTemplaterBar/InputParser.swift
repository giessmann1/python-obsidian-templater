import Foundation

enum EntryKind {
    case doi, ais

    /// The obsidian-templater.py flag that takes this kind of entry.
    var flag: String { self == .doi ? "-doi" : "-ais" }
}

struct Entry {
    let text: String
    let kind: EntryKind
}

enum InputParser {
    // Same rule as is_ais_paper in batch_process.sh
    private static let aisPrefix = try! NSRegularExpression(
        pattern: "^(icis|amcis|ecis|pacis|hicss|misqe|jais|cais|misq)[0-9]*")

    /// One entry per non-empty line; lines starting with # are ignored.
    static func parse(_ input: String) -> [Entry] {
        input.split(whereSeparator: \.isNewline).compactMap { rawLine in
            let line = rawLine.trimmingCharacters(in: .whitespaces)
            if line.isEmpty || line.hasPrefix("#") { return nil }
            return Entry(text: line, kind: isAIS(line) ? .ais : .doi)
        }
    }

    static func isAIS(_ line: String) -> Bool {
        if line.contains("aisel.aisnet.org") { return true }
        let range = NSRange(line.startIndex..., in: line)
        return aisPrefix.firstMatch(in: line, range: range) != nil
    }
}
