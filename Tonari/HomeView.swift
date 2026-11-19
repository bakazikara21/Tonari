//
//  HomeView.swift
//  Tonari
//

import SwiftUI

/// ホーム画面で選べる行き先
enum HomeDestination: Hashable {
    case page(ServerPage)
    case howTo
}

/// アプリを開いたときの画面。大きなボタンを3つ並べる。
/// ご家族向けの設定はここには出さず、「使い方」の一番下に置く。
struct HomeView: View {
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    HomeButton(title: "苦手なスイーツを教える", systemImage: "hand.raised", style: .primary,
                               destination: .page(.preferences))
                    HomeButton(title: "今日のおすすめ", systemImage: "gift", style: .primary,
                               destination: .page(.recommendation))
                    HomeButton(title: "使い方", systemImage: "questionmark.circle", style: .secondary,
                               destination: .howTo)
                }
                .padding(20)
            }
            .navigationTitle("Tonari")
            .navigationDestination(for: HomeDestination.self) { destination in
                switch destination {
                case .page(let page):
                    ServerPageView(page: page)
                case .howTo:
                    HowToView()
                }
            }
        }
    }
}

/// ホーム画面の大きなボタン
private struct HomeButton: View {
    enum Style {
        case primary, secondary
    }

    let title: String
    let systemImage: String
    let style: Style
    let destination: HomeDestination

    var body: some View {
        NavigationLink(value: destination) {
            Label(title, systemImage: systemImage)
                .font(.largeTitle.bold())
                .frame(maxWidth: .infinity, minHeight: 120)
                .foregroundStyle(style == .primary ? Color.white : Color.primary)
                .background(style == .primary ? Color.tonariOrange : Color(.systemBackground),
                            in: RoundedRectangle(cornerRadius: 24))
                .overlay {
                    if style == .secondary {
                        RoundedRectangle(cornerRadius: 24).stroke(Color.primary, lineWidth: 3)
                    }
                }
        }
        .buttonStyle(.plain)
    }
}

extension Color {
    /// Web ページ・拡張機能の「たすけて」ボタンと同じオレンジ(#C2410C)
    static let tonariOrange = Color(red: 0xC2 / 255, green: 0x41 / 255, blue: 0x0C / 255)
}

#Preview {
    HomeView()
}
