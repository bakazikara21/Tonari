//
//  ExtensionScript.swift
//  TonariTests
//

import Foundation

/// テストから Safari 拡張機能の JS ファイルを読み込むためのヘルパー。
/// シミュレータ上のテストは Mac のファイルを読めるので、ソースの場所から直接読む。
enum ExtensionScript {
    static func source(_ fileName: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // TonariTests
            .deletingLastPathComponent()      // プロジェクト直下
            .appendingPathComponent("Tonari Extension/Resources")
            .appendingPathComponent(fileName)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
