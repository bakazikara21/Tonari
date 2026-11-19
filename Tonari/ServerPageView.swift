//
//  ServerPageView.swift
//  Tonari
//

import SwiftUI
import WebKit

/// 中継サーバーの Web ページを、アプリの中に表示する画面。
/// つながらないときは決まった文を出し、もう一度読み込めるようにする。
/// ページの「終了する」ボタンが押されたら、この画面を閉じてホーム画面に戻る。
struct ServerPageView: View {
    let page: ServerPage

    @Environment(\.dismiss) private var dismiss

    @State private var state: LoadState = .loading
    /// 変えると Web ページを読み込み直す
    @State private var reloadToken = UUID()

    enum LoadState {
        case loading, loaded, failed
    }

    var body: some View {
        ZStack {
            ServerWebView(url: AppConfig.url(for: page), reloadToken: reloadToken) { newState in
                state = newState
            } onClose: {
                dismiss()
            }
            .opacity(state == .failed ? 0 : 1)

            switch state {
            case .loading:
                ProgressView()
                    .controlSize(.large)
            case .failed:
                UnavailableView {
                    state = .loading
                    reloadToken = UUID()
                }
            case .loaded:
                EmptyView()
            }
        }
        .navigationTitle(page.title)
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// つながらないときに出す画面
private struct UnavailableView: View {
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "wifi.exclamationmark")
                .font(.system(size: 64))
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text("いまは表示できません。あとでもう一度お試しください")
                .font(.title.bold())
                .multilineTextAlignment(.center)
            Button(action: retry) {
                Text("もう一度")
                    .font(.title.bold())
                    .frame(maxWidth: .infinity, minHeight: 72)
            }
            .buttonStyle(.borderedProminent)
            .tint(.tonariOrange)
        }
        .padding(24)
    }
}

/// WKWebView を SwiftUI で使うための包み
private struct ServerWebView: UIViewRepresentable {
    /// ページからアプリへ送る知らせの名前(ページ側は window.webkit.messageHandlers.tonari で送る)
    static let messageHandlerName = "tonari"

    let url: URL
    let reloadToken: UUID
    let onStateChange: (ServerPageView.LoadState) -> Void
    let onClose: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onStateChange: onStateChange, onClose: onClose)
    }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        // 「終了する」の知らせを受け取る。Coordinator を直接登録すると互いに離せなくなるので、弱い参照の中継を挟む
        configuration.userContentController.add(
            WeakMessageHandler(context.coordinator), name: Self.messageHandlerName
        )
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        context.coordinator.load(url, in: webView, token: reloadToken)
        return webView
    }

    static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
        webView.configuration.userContentController.removeScriptMessageHandler(forName: messageHandlerName)
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        context.coordinator.onStateChange = onStateChange
        context.coordinator.onClose = onClose
        // 「もう一度」が押されたときだけ読み込み直す
        if context.coordinator.loadedToken != reloadToken {
            context.coordinator.load(url, in: webView, token: reloadToken)
        }
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var onStateChange: (ServerPageView.LoadState) -> Void
        var onClose: () -> Void
        private(set) var loadedToken: UUID?

        init(onStateChange: @escaping (ServerPageView.LoadState) -> Void, onClose: @escaping () -> Void) {
            self.onStateChange = onStateChange
            self.onClose = onClose
        }

        // ページの「終了する」ボタンからの知らせ。中継サーバーのページから届いた "close" だけを受け付ける
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == ServerWebView.messageHandlerName,
                  message.body as? String == "close",
                  message.frameInfo.isMainFrame,
                  let url = message.webView?.url, AppConfig.isServerURL(url) else { return }
            onClose()
        }

        func load(_ url: URL, in webView: WKWebView, token: UUID) {
            loadedToken = token
            // キャッシュを使わず、毎回中継サーバーから読む
            // (キャッシュから表示すると、サーバーにつながらないことに気づけないため)
            webView.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalAndRemoteCacheData, timeoutInterval: 15))
        }

        // 中継サーバー以外のページへは移動しない(アプリの中で知らないページを開かないため)
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction) async -> WKNavigationActionPolicy {
            guard let url = navigationAction.request.url else { return .cancel }
            if url.scheme == "about" || AppConfig.isServerURL(url) {
                return .allow
            }
            return .cancel
        }

        // サーバーがエラー(404・500 など)を返したページは表示しない
        func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse) async -> WKNavigationResponsePolicy {
            if let response = navigationResponse.response as? HTTPURLResponse,
               navigationResponse.isForMainFrame,
               response.statusCode >= 400 {
                onStateChange(.failed)
                return .cancel
            }
            return .allow
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            onStateChange(.loaded)
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            reportFailure(error)
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            reportFailure(error)
        }

        /// 読み込みの失敗を伝える。こちらで止めた移動(中継サーバー以外へのリンク等)は失敗として扱わない。
        private func reportFailure(_ error: Error) {
            let error = error as NSError
            let cancelled = error.domain == NSURLErrorDomain && error.code == NSURLErrorCancelled
            // 「Frame load interrupted」(こちらが移動を止めたときに WebKit が返す)
            let stoppedByPolicy = error.domain == "WebKitErrorDomain" && error.code == 102
            if cancelled || stoppedByPolicy { return }
            onStateChange(.failed)
        }

        // Web ページの処理が落ちたときは、読み込み直す
        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            webView.reload()
        }
    }
}

/// WKUserContentController は登録した相手を強く持つので、Coordinator を弱く持つ中継を挟む
private final class WeakMessageHandler: NSObject, WKScriptMessageHandler {
    private weak var target: WKScriptMessageHandler?

    init(_ target: WKScriptMessageHandler) {
        self.target = target
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        target?.userContentController(userContentController, didReceive: message)
    }
}

#Preview {
    NavigationStack {
        ServerPageView(page: .recommendation)
    }
}
