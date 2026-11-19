//
//  ServerConfigTests.swift
//  TonariTests
//

import Foundation
import Testing
@testable import Tonari

struct ServerConfigTests {

    @Test func シミュレータでは設定ファイルがあってもMac自身につなぐ() {
        let url = ServerConfig.resolveBaseURL(
            isSimulator: true,
            localSettings: ["ServerURL": "http://my-mac.local:8000"]
        )
        #expect(url.absoluteString == "http://localhost:8000")
    }

    @Test(arguments: [
        "http://my-mac.local:8000",
        "http://my-mac.local:8000/",     // 末尾の / は取り除く
    ])
    func 実機では設定ファイルのURLにつなぐ(text: String) {
        let url = ServerConfig.resolveBaseURL(isSimulator: false, localSettings: ["ServerURL": text])
        #expect(url.absoluteString == "http://my-mac.local:8000")
    }

    @Test(arguments: [
        "",                                 // 空
        "my-mac.local:8000",                // 方式がない
        "ftp://my-mac.local",               // http / https 以外
        "http://my-mac.local:8000/guide",   // サーバーの場所以外まで書いてある
    ])
    func 実機で設定が正しくないときはlocalhostにする(text: String) {
        let url = ServerConfig.resolveBaseURL(isSimulator: false, localSettings: ["ServerURL": text])
        #expect(url == ServerConfig.simulatorURL)
    }

    @Test func 実機で設定ファイルがないときはlocalhostにする() {
        #expect(ServerConfig.resolveBaseURL(isSimulator: false, localSettings: nil) == ServerConfig.simulatorURL)
        // 文字ではない値
        #expect(ServerConfig.resolveBaseURL(isSimulator: false, localSettings: ["ServerURL": 8000]) == ServerConfig.simulatorURL)
    }
}
