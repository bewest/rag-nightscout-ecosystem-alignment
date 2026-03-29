// swift-tools-version: 6.0
// T1PalAdapterCLI — JSON-over-stdio bridge for the test harness
//
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Reads adapter-input JSON from stdin, runs T1PalAlgorithm, writes
// adapter-output JSON to stdout.  Supports modes: execute, validate-input, describe.

import PackageDescription

let package = Package(
    name: "T1PalAdapterCLI",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(path: "../../../t1pal-mobile-apex"),
    ],
    targets: [
        .executableTarget(
            name: "T1PalAdapterCLI",
            dependencies: [
                .product(name: "T1PalAlgorithm", package: "t1pal-mobile-apex"),
                .product(name: "T1PalCore", package: "t1pal-mobile-apex"),
            ],
            path: "Sources",
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
    ]
)
