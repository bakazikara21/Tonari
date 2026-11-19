//
//  DangerCheckTests.swift
//  TonariTests
//

import JavaScriptCore
import Testing

struct DangerCheckTests {

    /// danger-check.js を読み込み、looksLikeScam の結果を返す
    func looksLikeScam(_ text: String) throws -> Bool {
        let context = try #require(JSContext())
        context.evaluateScript(try ExtensionScript.source("danger-check.js"))
        context.setObject(text, forKeyedSubscript: "pageTextForTest" as NSString)
        return try #require(context.evaluateScript("TonariDangerCheck.looksLikeScam(pageTextForTest)")).toBool()
    }

    @Test(arguments: [
        "警告!お使いのiPhoneはウイルスに感染しています",
        "あなたのスマホがハッキングされています",
        "今すぐお電話ください 0120-xxx-xxx",
        "サポートセンターに今すぐ電話してください",
        "残り 60 秒でデータが削除されます",
        "おめでとうございます!あなたは当選しました",
        "お客様のアカウントは停止されました",
        "ギフトカードを購入して番号を入力してください",
        "Virus detected on your device",
        "Your iPhone has been hacked",
        "Congratulations! You are the lucky winner",
    ])
    func 偽の警告や詐欺らしい文を判別できる(text: String) throws {
        #expect(try looksLikeScam(text))
    }

    @Test(arguments: [
        "会員登録 お名前 メールアドレス パスワード 次へ進む",
        "ウイルス対策ソフトのご案内",
        "お問い合わせはサポートセンターまで",
        "ログイン パスワードを忘れた方",
        "ご登録ありがとうございます",
    ])
    func 普通の画面は詐欺と判別しない(text: String) throws {
        #expect(try looksLikeScam(text) == false)
    }
}
