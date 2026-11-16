// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "ObsidianTemplaterBar",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(name: "ObsidianTemplaterBar")
    ]
)
