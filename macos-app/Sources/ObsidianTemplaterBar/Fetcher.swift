import Foundation

enum ItemStatus {
    case pending, running, created, exists, failed
}

struct FetchItem: Identifiable {
    let id = UUID()
    let entry: Entry
    var status: ItemStatus = .pending
}

/// Where the obsidian-templater checkout lives and how to run it.
struct TemplaterRepo {
    static let overrideKey = "repoPath"

    let url: URL

    /// The folder chosen in the app, else the one recorded in Info.plist by build.sh.
    static var current: TemplaterRepo? {
        let chosen = UserDefaults.standard.string(forKey: overrideKey) ?? ""
        let bundled = Bundle.main.object(forInfoDictionaryKey: "TemplaterRepoPath") as? String ?? ""
        let path = chosen.isEmpty ? bundled : chosen
        return path.isEmpty ? nil : TemplaterRepo(url: URL(fileURLWithPath: path))
    }

    var python: URL { url.appendingPathComponent(".env/bin/python") }
    var script: URL { url.appendingPathComponent("obsidian-templater.py") }

    /// Nil when runnable, otherwise what is missing.
    var problem: String? {
        let fm = FileManager.default
        if !fm.fileExists(atPath: script.path) { return "obsidian-templater.py not found in \(url.path)" }
        if !fm.isExecutableFile(atPath: python.path) { return "Python venv not found at \(python.path)" }
        return nil
    }
}

@MainActor
final class Fetcher: ObservableObject {
    @Published var input = ""
    @Published var localPDF: URL?
    @Published var items: [FetchItem] = []
    @Published var log = ""
    @Published var isRunning = false

    /// Pause between entries, as in batch_process.sh.
    private let pauseSeconds: UInt64 = 5
    private var task: Task<Void, Never>?
    private var process: Process?

    func start(entries: [Entry], repo: TemplaterRepo, arguments: @escaping (Entry) -> [String]) {
        guard !isRunning else { return }
        task = Task { await run(entries: entries, repo: repo, arguments: arguments) }
    }

    func stop() {
        task?.cancel()
        process?.terminate()
    }

    func run(entries: [Entry], repo: TemplaterRepo, arguments: (Entry) -> [String]) async {
        isRunning = true
        items = entries.map { FetchItem(entry: $0) }
        log = ""
        defer {
            isRunning = false
            process = nil
        }

        for index in items.indices {
            if Task.isCancelled { break }
            if index > 0 {
                try? await Task.sleep(nanoseconds: pauseSeconds * 1_000_000_000)
                if Task.isCancelled { break }
            }

            items[index].status = .running
            let args = arguments(items[index].entry)
            log += "$ obsidian-templater.py \(args.joined(separator: " "))\n"

            let logStart = log.endIndex
            let exitCode = await runScript(repo: repo, arguments: args)
            let output = log[logStart...]
            log += "\n"

            // Same outcome rule as batch_process.sh
            if output.contains("Paper already exists") {
                items[index].status = .exists
            } else if exitCode == 0 && output.contains("Note created") {
                items[index].status = .created
            } else {
                items[index].status = .failed
            }
        }

        for index in items.indices where items[index].status == .pending || items[index].status == .running {
            items[index].status = .failed
        }
    }

    private func runScript(repo: TemplaterRepo, arguments: [String]) async -> Int32 {
        let process = Process()
        process.executableURL = repo.python
        process.arguments = [repo.script.path] + arguments
        // The script reads directories.txt, templates/ and the SJR csv relative to the cwd
        process.currentDirectoryURL = repo.url

        var environment = ProcessInfo.processInfo.environment
        // The script spawns "python3 -m PyPaperBot"; make that resolve to the venv
        let venvBin = repo.python.deletingLastPathComponent().path
        environment["PATH"] = venvBin + ":" + (environment["PATH"] ?? "/usr/bin:/bin")
        environment["PYTHONUNBUFFERED"] = "1"
        process.environment = environment

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        process.standardInput = FileHandle.nullDevice
        self.process = process

        return await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    try process.run()
                } catch {
                    Task { @MainActor in self.log += "Could not start Python: \(error.localizedDescription)\n" }
                    continuation.resume(returning: -1)
                    return
                }
                let reader = pipe.fileHandleForReading
                while true {
                    let data = reader.availableData
                    if data.isEmpty { break }
                    let text = String(decoding: data, as: UTF8.self)
                    DispatchQueue.main.sync { self.appendOutput(text) }
                }
                process.waitUntilExit()
                continuation.resume(returning: process.terminationStatus)
            }
        }
    }

    private func appendOutput(_ text: String) {
        // Drop ANSI colour codes the script uses for warnings
        log += text.replacingOccurrences(of: "\u{1B}\\[[0-9;]*m", with: "", options: .regularExpression)
    }
}
