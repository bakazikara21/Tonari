//
//  CollectorTests.swift
//  TonariTests
//

import Foundation
import Testing
import WebKit

/// collector.js が返す一覧の1項目
struct CollectedItem: Decodable, Equatable {
    struct Rect: Decodable, Equatable {
        let x: Int
        let y: Int
        let width: Int
        let height: Int
    }
    let id: Int
    let kind: String
    let label: String
    let rect: Rect
    // 入力の状態(種類によって付かないものは nil)
    var filled: Bool?
    var checked: Bool?
    var invalid: Bool?
}

/// WKWebView に HTML を読み込み、ページ内で collector.js を動かす
@MainActor
final class CollectorHarness: NSObject, WKNavigationDelegate {
    let webView = WKWebView(frame: CGRect(x: 0, y: 0, width: 390, height: 844))
    private var continuation: CheckedContinuation<Void, Error>?

    func load(_ html: String) async throws {
        webView.navigationDelegate = self
        try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            webView.loadHTMLString(html, baseURL: nil)
        }
    }

    /// setupScript を先に実行してから要素を集め、一覧を JSON 文字列で返す
    func collectJSON(setupScript: String = "") async throws -> String {
        let source = try ExtensionScript.source("collector.js")
        let body = """
        \(source)
        \(setupScript)
        return JSON.stringify(TonariCollector.collectVisibleElements(document, window).items);
        """
        let result = try await webView.callAsyncJavaScript(body, contentWorld: .page)
        return try #require(result as? String)
    }

    func collect(setupScript: String = "") async throws -> [CollectedItem] {
        let json = try await collectJSON(setupScript: setupScript)
        return try JSONDecoder().decode([CollectedItem].self, from: Data(json.utf8))
    }

    /// 任意の式を評価して真偽値を返す
    func evaluateBool(_ expression: String) async throws -> Bool {
        let result = try await webView.callAsyncJavaScript("return \(expression);", contentWorld: .page)
        return try #require(result as? Bool)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        continuation?.resume()
        continuation = nil
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        continuation?.resume(throwing: error)
        continuation = nil
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        continuation?.resume(throwing: error)
        continuation = nil
    }
}

@MainActor
struct CollectorTests {

    /// 会員登録画面を想定したページ
    static let signupPage = """
    <!DOCTYPE html>
    <html><head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body { margin: 0; font-size: 16px; } .far { position: absolute; top: 3000px; }</style>
    </head><body>
    <a href="/terms">利用規約</a>
    <label for="name">お名前</label><input id="name" type="text" value="山田太郎">
    <input type="email" aria-label="メールアドレス" placeholder="例: taro@example.com">
    <label>パスワード <input id="pw" type="password" value="secret-pass-123"></label>
    <input type="tel" name="pin_code" placeholder="暗証番号(4桁)" value="9876">
    <label>カード番号 <input type="text" autocomplete="cc-number" value="4111111111111111"></label>
    <select aria-label="都道府県"><option>東京都</option></select>
    <textarea placeholder="ご意見">なかのぶんしょう</textarea>
    <label><input type="checkbox"> お知らせメールを受け取る</label>
    <button type="submit">次へ進む</button>
    <input type="submit" value="登録する">

    <!-- 以下は集めてはいけないもの -->
    <input type="hidden" name="token" value="x">
    <button style="display: none">見えないボタン</button>
    <button style="visibility: hidden">隠れたボタン</button>
    <button style="opacity: 0">透明なボタン</button>
    <button disabled>押せないボタン</button>
    <button class="far">画面外のボタン</button>
    </body></html>
    """

    @Test func 見えている操作できる要素を順番どおりに種類とラベル付きで集める() async throws {
        let harness = CollectorHarness()
        try await harness.load(Self.signupPage)
        let items = try await harness.collect()

        let summary = items.map { "\($0.kind):\($0.label)" }
        #expect(summary == [
            "link:利用規約",
            "text-input:お名前",
            "text-input:メールアドレス",
            "password:",
            "secret:",
            "secret:",
            "select:都道府県",
            "textarea:ご意見",
            "checkbox:お知らせメールを受け取る",
            "button:次へ進む",
            "button:登録する",
        ])
        #expect(items.map(\.id) == Array(1...items.count))
    }

    @Test func 見えない要素_押せない要素_画面外の要素は集めない() async throws {
        let harness = CollectorHarness()
        try await harness.load(Self.signupPage)
        let labels = try await harness.collect().map(\.label)

        for hidden in ["見えないボタン", "隠れたボタン", "透明なボタン", "押せないボタン", "画面外のボタン"] {
            #expect(!labels.contains(hidden))
        }
    }

    @Test func 入力欄の値は一覧に含めない() async throws {
        let harness = CollectorHarness()
        try await harness.load(Self.signupPage)
        // 利用者が入力したことにする
        let json = try await harness.collectJSON(setupScript: """
        document.getElementById("pw").value = "typed-secret-999";
        document.getElementById("name").value = "入力された名前";
        """)

        for value in ["secret-pass-123", "typed-secret-999", "9876", "4111111111111111",
                      "山田太郎", "入力された名前", "なかのぶんしょう", "東京都"] {
            #expect(!json.contains(value), "一覧に値が含まれている: \(value)")
        }
    }

    @Test func 秘密の欄は入力済みかどうかだけが一覧に出る() async throws {
        let page = """
        <!DOCTYPE html>
        <html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body>
        <input id="pw" type="password" aria-invalid="true">
        <input id="pin" type="tel" name="pin">
        <input id="card" type="text" autocomplete="cc-number">
        </body></html>
        """
        let harness = CollectorHarness()
        try await harness.load(page)
        let empty = try await harness.collect()
        let filledJSON = try await harness.collectJSON(setupScript: """
        document.getElementById("pw").value = "secret-pass";
        document.getElementById("pin").value = "1234";
        document.getElementById("card").value = "4111111111111111";
        """)
        let filled = try JSONDecoder().decode([CollectedItem].self, from: Data(filledJSON.utf8))

        // 値は一覧に入らない
        for value in ["secret-pass", "1234", "4111111111111111"] {
            #expect(!filledJSON.contains(value))
        }
        // 入力済みかどうかだけが変わる。ラベル・チェック・誤りの印は付かない。
        #expect(empty.map(\.filled) == [false, false, false])
        #expect(filled.map(\.filled) == [true, true, true])
        for item in empty + filled {
            #expect(["password", "secret"].contains(item.kind))
            #expect(item.label == "")
            #expect(item.checked == nil)
            #expect(item.invalid == nil)
        }
        let withoutFilled = filled.map { item -> CollectedItem in
            var copy = item
            copy.filled = false
            return copy
        }
        #expect(withoutFilled == empty)
    }

    @Test func 普通の欄は入力済み_チェック済み_誤りの印を記録する() async throws {
        let harness = CollectorHarness()
        try await harness.load("""
        <!DOCTYPE html>
        <html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body>
        <input id="name" aria-label="お名前">
        <input id="mail" type="email" aria-label="メールアドレス" aria-invalid="true">
        <select aria-label="都道府県"><option value="">選んでください</option><option value="13">東京都</option></select>
        <label><input id="agree" type="checkbox"> 利用規約に同意する</label>
        <label><input type="radio" name="mag"> メールを受け取る</label>
        <button>次へ</button>
        </body></html>
        """)
        let items = try await harness.collect(setupScript: """
        document.getElementById("name").value = "山田太郎";
        document.getElementById("agree").checked = true;
        """)

        let states = items.map { "\($0.label):\(String(describing: $0.filled)):\(String(describing: $0.checked)):\(String(describing: $0.invalid))" }
        #expect(states == [
            "お名前:Optional(true):nil:Optional(false)",
            "メールアドレス:Optional(false):nil:Optional(true)",
            "都道府県:Optional(false):nil:Optional(false)",
            "利用規約に同意する:nil:Optional(true):Optional(false)",
            "メールを受け取る:nil:Optional(false):Optional(false)",
            "次へ:nil:nil:nil",
        ])
    }

    @Test(arguments: [
        #"<input type="password" aria-label="ログイン用">"#,
        #"<input type="text" name="pwd">"#,
        #"<input type="text" name="passcode">"#,
        #"<input type="tel" name="pinCode">"#,
        #"<input type="text" id="card_number">"#,
        #"<input type="text" autocomplete="cc-csc">"#,
        #"<input type="text" autocomplete="one-time-code">"#,
        #"<label>暗証番号 <input type="tel"></label>"#,
        #"<input type="text" placeholder="カード番号">"#,
    ])
    func 種類や名前から秘密の欄と判別し_ラベルを残さない(field: String) async throws {
        let harness = CollectorHarness()
        try await harness.load("""
        <!DOCTYPE html>
        <html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body>\(field)</body></html>
        """)
        let items = try await harness.collect()

        #expect(items.count == 1)
        #expect(["password", "secret"].contains(items.first?.kind ?? ""))
        #expect(items.first?.label == "")
    }

    @Test func 要素の位置を画面上の座標で記録する() async throws {
        let harness = CollectorHarness()
        try await harness.load("""
        <!DOCTYPE html>
        <html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
        <body style="margin: 0">
        <button style="position: absolute; left: 20px; top: 100px; width: 200px; height: 50px; margin: 0">次へ</button>
        </body></html>
        """)
        let items = try await harness.collect()

        #expect(items == [
            CollectedItem(id: 1, kind: "button", label: "次へ",
                          rect: .init(x: 20, y: 100, width: 200, height: 50)),
        ])
    }

    @Test func パスワードを忘れた方へのリンクは秘密の欄として扱わない() async throws {
        let harness = CollectorHarness()
        try await harness.load("""
        <!DOCTYPE html>
        <html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
        <body><a href="/forgot">パスワードを忘れた方</a><input name="shipping_address" aria-label="住所"></body></html>
        """)
        let summary = try await harness.collect().map { "\($0.kind):\($0.label)" }

        #expect(summary == ["link:パスワードを忘れた方", "text-input:住所"])
    }
}
