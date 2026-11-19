//
//  ValidatorTests.swift
//  TonariTests
//

import Foundation
import JavaScriptCore
import Testing

struct ValidatorTests {

    /// テストで使う要素の一覧(collector.js が返す形)
    static let items = """
    [
      { "id": 1, "kind": "text-input", "label": "お名前", "rect": { "x": 0, "y": 0, "width": 100, "height": 40 } },
      { "id": 2, "kind": "password", "label": "", "rect": { "x": 0, "y": 50, "width": 100, "height": 40 } },
      { "id": 3, "kind": "button", "label": "次へ進む", "rect": { "x": 0, "y": 100, "width": 100, "height": 40 } },
      { "id": 4, "kind": "button", "label": "購入を確定する", "rect": { "x": 0, "y": 150, "width": 100, "height": 40 } },
      { "id": 5, "kind": "link", "label": "注文する", "rect": { "x": 0, "y": 200, "width": 100, "height": 40 } },
      { "id": 6, "kind": "button", "label": "Buy now", "rect": { "x": 0, "y": 250, "width": 100, "height": 40 } },
      { "id": 7, "kind": "text-input", "label": "ご注文番号", "rect": { "x": 0, "y": 300, "width": 100, "height": 40 } }
    ]
    """

    /// validator.js を読み込み、validateGuide の結果を辞書で返す
    func validate(response: String, items: String = Self.items) throws -> [String: Any] {
        let context = try #require(JSContext())
        context.evaluateScript(try ExtensionScript.source("validator.js"))
        let json = try #require(
            context.evaluateScript("JSON.stringify(TonariValidator.validateGuide(\(response), \(items)))")?.toString()
        )
        let object = try JSONSerialization.jsonObject(with: Data(json.utf8))
        return try #require(object as? [String: Any])
    }

    @Test(arguments: [1, 2, 3, 7])
    func 実在する番号なら成功し_その要素を返す(targetId: Int) throws {
        let result = try validate(response: #"{ "message": "ここを押してください", "targetId": \#(targetId) }"#)

        #expect(result["ok"] as? Bool == true)
        #expect(result["message"] as? String == "ここを押してください")
        let target = try #require(result["target"] as? [String: Any])
        #expect(target["id"] as? Int == targetId)
    }

    @Test(arguments: ["0", "-1", "8", "99"])
    func 一覧にない番号は失敗する(targetId: String) throws {
        let result = try validate(response: #"{ "message": "ここを押してください", "targetId": \#(targetId) }"#)

        #expect(result["ok"] as? Bool == false)
        #expect(result["reason"] as? String == "unknown-target-id")
    }

    @Test(arguments: [#""1""#, "1.5", "true", "[1]", #"{ "id": 1 }"#, "NaN"])
    func 整数でない番号は失敗する(targetId: String) throws {
        let result = try validate(response: #"{ "message": "ここを押してください", "targetId": \#(targetId) }"#)

        #expect(result["ok"] as? Bool == false)
        #expect(result["reason"] as? String == "invalid-target-id")
    }

    @Test func 番号がない案内は文だけで成功する() throws {
        let result = try validate(response: #"{ "message": "入力欄がありません", "targetId": null }"#)

        #expect(result["ok"] as? Bool == true)
        #expect(result["target"] is NSNull)
    }

    @Test(arguments: [4, 5, 6])
    func 購入や注文を確定するボタンには枠を出さない(targetId: Int) throws {
        let result = try validate(response: #"{ "message": "ここを押してください", "targetId": \#(targetId) }"#)

        #expect(result["ok"] as? Bool == false)
        #expect(result["reason"] as? String == "commit-action")
    }

    @Test func サーバーが確定のボタンと判定したら枠を出さない() throws {
        let result = try validate(response: #"{ "message": "ここから先はご自身で内容を確かめてください。", "targetId": null, "warning": "commit-action" }"#)

        #expect(result["ok"] as? Bool == false)
        #expect(result["reason"] as? String == "commit-action")
    }

    @Test func サーバーが詐欺を疑ったら番号があっても枠を出さない() throws {
        let result = try validate(response: #"{ "message": "ここを押してください", "targetId": 1, "warning": "scam" }"#)

        #expect(result["ok"] as? Bool == false)
        #expect(result["reason"] as? String == "scam")
    }

    @Test(arguments: [

        #"{ "targetId": 1 }"#,
        #"{ "message": "", "targetId": 1 }"#,
        #"{ "message": "   ", "targetId": 1 }"#,
        #"{ "message": 123, "targetId": 1 }"#,
    ])
    func 案内文がない応答は失敗する(response: String) throws {
        let result = try validate(response: response)

        #expect(result["ok"] as? Bool == false)
        #expect(result["reason"] as? String == "no-message")
    }

    @Test func 長すぎる案内文は失敗する() throws {
        let longMessage = String(repeating: "あ", count: 201)
        let result = try validate(response: #"{ "message": "\#(longMessage)", "targetId": 1 }"#)

        #expect(result["ok"] as? Bool == false)
        #expect(result["reason"] as? String == "message-too-long")
    }

    @Test(arguments: ["null", "undefined", #""ここを押して""#, "42"])
    func オブジェクトでない応答は失敗する(response: String) throws {
        let result = try validate(response: response)

        #expect(result["ok"] as? Bool == false)
        #expect(result["reason"] as? String == "not-object")
    }

    @Test func 一覧が配列でなければ失敗する() throws {
        let result = try validate(response: #"{ "message": "ここ", "targetId": 1 }"#, items: "null")

        #expect(result["ok"] as? Bool == false)
        #expect(result["reason"] as? String == "no-items")
    }
}
