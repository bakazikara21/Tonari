//
//  AppConfigTests.swift
//  TonariTests
//

import Foundation
import Testing
@testable import Tonari

struct AppConfigTests {

    @Test(arguments: [
        (ServerPage.recommendation, "/recommendation"),
        (ServerPage.preferences, "/preferences"),
        (ServerPage.settings, "/settings"),
    ])
    func 各ページのURLは中継サーバーのURLから作る(page: ServerPage, path: String) {
        let url = AppConfig.url(for: page)

        #expect(url.absoluteString == AppConfig.serverBaseURL.absoluteString + path)
        #expect(AppConfig.isServerURL(url))
    }

    @Test(arguments: [
        "https://example.com/preferences",            // 別のサイト
        "http://127.0.0.1:9999/preferences",          // 同じ機械でも別のポート
        "https://127.0.0.1:8000/preferences",         // 別の方式
    ])
    func 中継サーバー以外のURLはアプリの中で開かない(text: String) throws {
        let url = try #require(URL(string: text))
        #expect(!AppConfig.isServerURL(url))
    }
}
