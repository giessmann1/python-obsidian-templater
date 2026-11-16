import AppKit
import SwiftUI

struct ContentView: View {
    @ObservedObject var fetcher: Fetcher

    @AppStorage("readingList") private var readingList = false
    @AppStorage("skipPDF") private var skipPDF = false
    @AppStorage("forceType") private var forceType = ""
    @AppStorage("relatedProjects") private var relatedProjects = ""
    @AppStorage(TemplaterRepo.overrideKey) private var repoOverride = ""
    @State private var showLog = false

    private let types = ["conference", "journal", "book", "chapter", "misc"]

    private var entries: [Entry] { InputParser.parse(fetcher.input) }
    private var repo: TemplaterRepo? {
        _ = repoOverride  // re-evaluate when the folder is changed
        return TemplaterRepo.current
    }
    private var repoProblem: String? {
        guard let repo else { return "Templater folder not set. Choose it from the gear menu." }
        return repo.problem
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("DOIs or AIS links, one per line")
                .font(.caption)
                .foregroundStyle(.secondary)

            TextEditor(text: $fetcher.input)
                .font(.system(.body, design: .monospaced))
                .frame(height: 90)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.secondary.opacity(0.4)))
                .disabled(fetcher.isRunning)

            HStack(spacing: 16) {
                Toggle("Reading list", isOn: $readingList)
                Toggle("Skip PDF", isOn: $skipPDF)
            }

            Picker("Type", selection: $forceType) {
                Text("Auto-detect").tag("")
                ForEach(types, id: \.self) { Text($0.capitalized).tag($0) }
            }

            TextField("Related projects, e.g. [[Project A]], [[Project B]]", text: $relatedProjects)
                .textFieldStyle(.roundedBorder)

            HStack {
                Button("Local PDF…", action: chooseLocalPDF)
                    .disabled(entries.count != 1)
                if let pdf = fetcher.localPDF {
                    Text(pdf.lastPathComponent)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Button {
                        fetcher.localPDF = nil
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                    }
                    .buttonStyle(.plain)
                    .help("Remove local PDF")
                } else {
                    Text(entries.count > 1 ? "Only with a single entry" : "None")
                        .foregroundStyle(.secondary)
                }
            }

            if let repoProblem {
                Label(repoProblem, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }

            HStack {
                if fetcher.isRunning {
                    Button("Stop", role: .cancel) { fetcher.stop() }
                    ProgressView().controlSize(.small)
                } else {
                    Button("Fetch", action: fetch)
                        .keyboardShortcut(.return, modifiers: .command)
                        .buttonStyle(.borderedProminent)
                        .disabled(entries.isEmpty || repoProblem != nil)
                }
                Spacer()
                Menu {
                    Button("Templater folder…", action: chooseRepo)
                    Divider()
                    Button("Quit") { NSApp.terminate(nil) }
                } label: {
                    Image(systemName: "gearshape")
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
            }

            if !fetcher.items.isEmpty {
                Divider()
                ScrollView {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(fetcher.items) { item in
                            HStack(spacing: 6) {
                                statusIcon(item.status)
                                Text(item.entry.text)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                                Spacer()
                                Text(statusText(item.status))
                                    .foregroundStyle(.secondary)
                            }
                            .font(.callout)
                        }
                    }
                }
                .frame(maxHeight: 110)

                DisclosureGroup("Log", isExpanded: $showLog) {
                    ScrollView {
                        Text(fetcher.log)
                            .font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(height: 150)
                }
            }
        }
        .padding(14)
        .frame(width: 400)
    }

    private func fetch() {
        guard let repo else { return }
        let entries = self.entries
        let single = entries.count == 1
        let localPDF = fetcher.localPDF
        let readingList = self.readingList
        let skipPDF = self.skipPDF
        let forceType = self.forceType
        let projects = relatedProjects.trimmingCharacters(in: .whitespaces)

        fetcher.start(entries: entries, repo: repo) { entry in
            var args = [entry.kind.flag, entry.text]
            if readingList { args.append("-readinglist") }
            if skipPDF { args.append("--skip-pdf") }
            // The script only honours --force-type for DOIs
            if entry.kind == .doi && !forceType.isEmpty { args += ["--force-type", forceType] }
            if !projects.isEmpty { args += ["--related-projects", projects] }
            if single, let localPDF { args += ["--local-pdf", localPDF.path] }
            return args
        }
    }

    private func chooseLocalPDF() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.pdf]
        panel.allowsMultipleSelection = false
        NSApp.activate(ignoringOtherApps: true)
        if panel.runModal() == .OK { fetcher.localPDF = panel.url }
    }

    private func chooseRepo() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.message = "Choose the folder that contains obsidian-templater.py"
        NSApp.activate(ignoringOtherApps: true)
        if panel.runModal() == .OK, let url = panel.url { repoOverride = url.path }
    }

    @ViewBuilder
    private func statusIcon(_ status: ItemStatus) -> some View {
        switch status {
        case .pending: Image(systemName: "circle").foregroundStyle(.secondary)
        case .running: ProgressView().controlSize(.mini)
        case .created: Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
        case .exists: Image(systemName: "equal.circle.fill").foregroundStyle(.secondary)
        case .failed: Image(systemName: "xmark.circle.fill").foregroundStyle(.red)
        }
    }

    private func statusText(_ status: ItemStatus) -> String {
        switch status {
        case .pending: return "waiting"
        case .running: return "fetching"
        case .created: return "created"
        case .exists: return "already exists"
        case .failed: return "failed"
        }
    }
}
