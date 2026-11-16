import SwiftUI

@main
enum Main {
    @MainActor
    static func main() {
        // "--headless [script flags] -- entry..." runs the fetch without UI (used for testing)
        if let index = CommandLine.arguments.firstIndex(of: "--headless") {
            runHeadless(Array(CommandLine.arguments[(index + 1)...]))
        } else {
            TemplaterApp.main()
        }
    }

    @MainActor
    private static func runHeadless(_ arguments: [String]) -> Never {
        let parts = arguments.split(separator: "--", maxSplits: 1, omittingEmptySubsequences: false)
        let flags = parts.count == 2 ? Array(parts[0]) : []
        let entries = InputParser.parse((parts.last ?? []).joined(separator: "\n"))

        guard let repo = TemplaterRepo.current, repo.problem == nil else {
            print(TemplaterRepo.current?.problem ?? "Templater folder not set")
            exit(2)
        }
        Task { @MainActor in
            let fetcher = Fetcher()
            await fetcher.run(entries: entries, repo: repo) { [$0.kind.flag, $0.text] + flags }
            print(fetcher.log)
            for item in fetcher.items { print("\(item.status)\t\(item.entry.text)") }
            exit(fetcher.items.contains { $0.status == .failed } ? 1 : 0)
        }
        RunLoop.main.run()
        exit(0)
    }
}

struct TemplaterApp: App {
    @StateObject private var fetcher = Fetcher()

    var body: some Scene {
        MenuBarExtra {
            ContentView(fetcher: fetcher)
        } label: {
            Image(systemName: fetcher.isRunning ? "arrow.triangle.2.circlepath" : "books.vertical")
        }
        .menuBarExtraStyle(.window)
    }
}
