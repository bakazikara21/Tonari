//
//  ShieldTests.swift
//  TonariTests
//

import Foundation
import Testing
import WebKit

@MainActor
struct ShieldTests {

    /// 「メニューの外が押されたら閉じる」処理を持つページ。
    /// 捕捉フェーズ・通常フェーズの両方で、受け取ったイベントを数える。
    static let menuPage = """
    <!DOCTYPE html>
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body style="margin: 0">
    <nav id="menu" style="height: 200px">メニュー</nav>
    <script>
      window.pageEvents = [];
      for (const type of ["touchstart", "pointerdown", "mousedown", "mouseup", "click"]) {
        document.addEventListener(type, () => pageEvents.push("capture:" + type), true);
        document.addEventListener(type, () => pageEvents.push("bubble:" + type));
      }
    </script>
    </body></html>
    """

    /// shield.js を読み込み、Tonari と同じ形(閉じた Shadow DOM の中のボタン)の画面を作る
    static let setupScript = """
    const host = document.createElement("div");
    host.style.cssText = "position: fixed; top: 0; left: 0; width: 0; height: 0;";
    const root = host.attachShadow({ mode: "closed" });
    root.innerHTML = '<button style="position: fixed; left: 100px; top: 400px; width: 160px; height: 60px">たすけて</button>';
    document.documentElement.appendChild(host);
    const button = root.querySelector("button");
    window.activated = [];
    TonariShield.attach(host, (event) => {
      const hit = root.elementFromPoint(event.clientX, event.clientY);
      if (hit === button) activated.push("たすけて");
    });

    // ボタンの中央を押したときと同じ順にイベントを送る
    function tap(target, x, y) {
      const options = { bubbles: true, composed: true, cancelable: true, clientX: x, clientY: y };
      target.dispatchEvent(new PointerEvent("pointerdown", options));
      target.dispatchEvent(new MouseEvent("mousedown", options));
      target.dispatchEvent(new MouseEvent("mouseup", options));
      target.dispatchEvent(new MouseEvent("click", options));
    }
    """

    func run(_ script: String) async throws -> [String: [String]] {
        let harness = CollectorHarness()
        try await harness.load(Self.menuPage)
        let shield = try ExtensionScript.source("shield.js")
        let result = try await harness.webView.callAsyncJavaScript("""
        \(shield)
        \(Self.setupScript)
        \(script)
        return JSON.stringify({ page: pageEvents, activated });
        """, contentWorld: .page)
        let json = try #require(result as? String)
        return try JSONDecoder().decode([String: [String]].self, from: Data(json.utf8))
    }

    @Test func Tonariのボタンを押してもページ側にはイベントが届かない() async throws {
        let result = try await run("tap(button, 180, 430);")

        #expect(result["page"] == [])
        #expect(result["activated"] == ["たすけて"])
    }

    @Test func ページ側の要素を押したときはページにそのまま届く() async throws {
        let result = try await run(#"tap(document.getElementById("menu"), 50, 50);"#)

        #expect(result["page"]?.contains("capture:click") == true)
        #expect(result["page"]?.contains("bubble:mousedown") == true)
        #expect(result["activated"] == [])
    }
}
