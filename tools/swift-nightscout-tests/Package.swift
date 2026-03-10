// swift-tools-version: 5.9
// Nightscout Integration Tests - Swift Client Simulation

import PackageDescription

let package = Package(
    name: "NightscoutTests",
    platforms: [.macOS(.v13)],
    products: [
        .library(name: "NightscoutTestKit", targets: ["NightscoutTestKit"]),
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-crypto.git", from: "3.0.0"),
    ],
    targets: [
        .target(
            name: "NightscoutTestKit",
            dependencies: [
                .product(name: "Crypto", package: "swift-crypto"),
            ],
            path: "Sources"
        ),
        .testTarget(
            name: "NightscoutTestKitTests",
            dependencies: ["NightscoutTestKit"],
            path: "Tests"
        ),
    ]
)
