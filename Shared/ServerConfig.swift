//
//  ServerConfig.swift
//  Tonari / Tonari Extension(両方のターゲットで使う)
//

import Foundation
import os

/// 中継サーバーの接続先。アプリと拡張機能の両方が、このファイルだけで接続先を決める。
///
/// - シミュレータ: Mac のネットワークをそのまま使うので、Mac 自身を指す localhost でつながる。
/// - 実機: iPhone の localhost は iPhone 自身なので、同じ Wi-Fi にある Mac の名前(○○.local)でつなぐ。
///   その URL は人ごとに違うため、Git に入れない設定ファイル Shared/LocalServer.plist に書く
///   (scripts/use-this-mac.sh で作る)。
nonisolated enum ServerConfig {
    /// シミュレータ用の接続先(Mac 自身)
    static let simulatorURL: URL = {
        guard let url = URL(string: "http://localhost:8000") else {
            preconditionFailure("中継サーバーの URL が正しくありません")
        }
        return url
    }()

    /// 実機用の設定ファイルの名前と、その中のキー
    static let localSettingsName = "LocalServer"
    static let localSettingsKey = "ServerURL"

    /// 中継サーバーの URL(末尾に / は付けない)
    static let baseURL: URL = {
        #if targetEnvironment(simulator)
        let isSimulator = true
        #else
        let isSimulator = false
        #endif
        let settings = Bundle.main.url(forResource: localSettingsName, withExtension: "plist")
            .flatMap { NSDictionary(contentsOf: $0) as? [String: Any] }
        return resolveBaseURL(isSimulator: isSimulator, localSettings: settings)
    }()

    /// 接続先を決める(テストしやすいように、端末の種類と設定ファイルの中身を引数で受け取る)
    static func resolveBaseURL(isSimulator: Bool, localSettings: [String: Any]?) -> URL {
        if isSimulator {
            return simulatorURL
        }
        // 「http://mac.local:8000/」のように末尾に / があっても同じ扱いにする
        let text = (localSettings?[localSettingsKey] as? String)?
            .trimmingCharacters(in: .whitespaces)
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let text,
              let url = URL(string: text),
              url.scheme == "http" || url.scheme == "https",
              url.host != nil,
              url.path.isEmpty,       // 「サーバーの場所」だけを書く(/guide などは各機能が足す)
              url.query == nil else {
            // 設定がないと実機ではつながらない。アプリはいつもの「つながらない」画面を出す
            Logger(subsystem: "io.github.bakazikara21.Tonari", category: "server")
                .error("Shared/LocalServer.plist がないか、ServerURL が正しくありません。scripts/use-this-mac.sh を実行してください")
            return simulatorURL
        }
        return url
    }
}
