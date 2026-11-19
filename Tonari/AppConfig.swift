//
//  AppConfig.swift
//  Tonari
//

import Foundation

/// アプリの設定。中継サーバーの接続先は Shared/ServerConfig.swift で決める(拡張機能と共通)。
enum AppConfig {
    /// 中継サーバーの URL
    static var serverBaseURL: URL { ServerConfig.baseURL }

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
