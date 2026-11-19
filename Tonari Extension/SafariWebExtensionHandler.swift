//
//  SafariWebExtensionHandler.swift
//  Tonari Extension
//
//  Created by 相川翔馬 on 2026/11/15.
//

import SafariServices
import os

/// 拡張機能の JS(guide-provider.js)から頼まれて、中継サーバーに案内を問い合わせる。
///
/// JS から直接 http で送らずにここを通すのは、次の2つのため。
/// - 接続先を Shared/ServerConfig.swift の1か所で決める(アプリと共通)。
/// - 実機では Mac の「○○.local」に http で送るが、Safari の拡張機能ページからの http 通信は
///   安全でない通信として止められることがある。
///
/// 送るのは JS が作った要素の一覧(パスワード等の値は collector.js の段階で含まれていない)。
/// ページの中身はログに残さない。
final class SafariWebExtensionHandler: NSObject, NSExtensionRequestHandling {
    /// 受け付ける依頼の種類(これ以外は断る)
    static let guideMessageType = "tonari:guide"
    /// サーバーが応答しないときに待つ時間(秒)
    static let timeout: TimeInterval = 20

    private static let logger = Logger(subsystem: "io.github.bakazikara21.Tonari.Extension", category: "guide")

    func beginRequest(with context: NSExtensionContext) {
        let item = context.inputItems.first as? NSExtensionItem
        let message = item?.userInfo?[SFExtensionMessageKey] as? [String: Any]

        // 案内の依頼で、JSON にできる中身のときだけ受け付ける
        guard message?["type"] as? String == Self.guideMessageType,
              let body = message?["body"] as? [String: Any],
              JSONSerialization.isValidJSONObject(body),
              let bodyData = try? JSONSerialization.data(withJSONObject: body) else {
            Self.complete(context, with: ["ok": false, "error": "bad-request"])
            return
        }

        // 送り先は /guide だけに固定する(JS から送り先を変えられないようにする)
        var request = URLRequest(
            url: ServerConfig.baseURL.appendingPathComponent("guide"),
            cachePolicy: .reloadIgnoringLocalAndRemoteCacheData,
            timeoutInterval: Self.timeout
        )
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = bodyData

        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error {
                // 原因が分かるように種類だけ残す(送った中身は残さない)
                Self.logger.error("中継サーバーにつながりませんでした: \((error as NSError).code)")
                Self.complete(context, with: ["ok": false, "error": "network"])
                return
            }
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard (200..<300).contains(status) else {
                Self.logger.error("中継サーバーがエラーを返しました: \(status)")
                Self.complete(context, with: ["ok": false, "error": "status-\(status)"])
                return
            }
            // 中身の検査は content.js 側(validator.js)で行う。ここでは JSON の形かどうかだけ見る
            guard let data,
                  let guide = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                Self.complete(context, with: ["ok": false, "error": "invalid-response"])
                return
            }
            Self.complete(context, with: ["ok": true, "guide": guide])
        }.resume()
    }

    /// JS へ返事を送る
    private static func complete(_ context: NSExtensionContext, with reply: [String: Any]) {
        let response = NSExtensionItem()
        response.userInfo = [SFExtensionMessageKey: reply]
        context.completeRequest(returningItems: [response], completionHandler: nil)
    }
}
