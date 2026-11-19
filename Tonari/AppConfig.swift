//
//  AppConfig.swift
//  Tonari
//

import Foundation

/// アプリの設定。中継サーバーの URL はここだけで決める。
enum AppConfig {
    /// 中継サーバーの URL。変更するときはここだけを書き換える。
    /// シミュレータからは Mac の中継サーバーにそのままつながる(server フォルダの uvicorn)。
    static let serverBaseURL: URL = {
        guard let url = URL(string: "http://127.0.0.1:8000") else {
            preconditionFailure("中継サーバーの URL が正しくありません")
        }
        return url
    }()

    /// 中継サーバーのページの URL
    static func url(for page: ServerPage) -> URL {
        serverBaseURL.appending(path: page.path)
    }

    /// アプリの中で表示してよい URL か(中継サーバーと同じ場所のページだけ)
    static func isServerURL(_ url: URL) -> Bool {
        url.scheme == serverBaseURL.scheme
            && url.host() == serverBaseURL.host()
            && url.port == serverBaseURL.port
    }
}

/// アプリの中で表示する、中継サーバーのページ
enum ServerPage: Hashable {
    case recommendation   // 今日のおすすめ
    case preferences      // 苦手なスイーツを教える
    case settings         // ご家族向けの設定

    var path: String {
        switch self {
        case .recommendation: "recommendation"
        case .preferences: "preferences"
        case .settings: "settings"
        }
    }

    var title: String {
        switch self {
        case .recommendation: "今日のおすすめ"
        case .preferences: "苦手なスイーツ"
        case .settings: "お勧めの設定"
        }
    }
}
