//
//  HowToView.swift
//  Tonari
//

import SwiftUI

/// 「使い方」の画面。Safari の拡張機能を有効にする手順を説明する。
/// 一番下に、ご家族向けの設定ページへの小さなリンクを置く(ホーム画面には出さない)。
struct HowToView: View {
    /// Safari の拡張機能を有効にする手順
    private let steps = [
        "「設定」アプリを開きます。",
        "「アプリ」を押し、「Safari」を押します。",
        "「機能拡張」を押します。",
        "「Tonari Extension」を押して、オンにします。",
        "「すべての Web サイト」を「許可」にします。",
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack(spacing: 16) {
                    // テンプレートにあったアプリのアイコン
                    if let icon = UIImage(named: "Icon") {
                        Image(uiImage: icon)
                            .resizable()
                            .frame(width: 72, height: 72)
                            .accessibilityHidden(true)
                    }
                    Text("Safari で「たすけて」ボタンを使えるようにします")
                        .font(.title2.bold())
                }

                VStack(alignment: .leading, spacing: 16) {
                    ForEach(Array(steps.enumerated()), id: \.offset) { index, step in
                        HStack(alignment: .firstTextBaseline, spacing: 12) {
                            Text("\(index + 1)")
                                .font(.title2.bold())
                                .foregroundStyle(.white)
                                .frame(width: 44, height: 44)
                                .background(Color.tonariOrange, in: Circle())
                                .accessibilityHidden(true)
                            Text(step)
                                .font(.title2)
                        }
                        .accessibilityElement(children: .combine)
                        .accessibilityLabel("手順\(index + 1)。\(step)")
                    }
                }

                Text("オンにすると、Safari でページを開いたときに、右下に「たすけて」ボタンが出ます。困ったときに押してください。")
                    .font(.title3)

                Divider()
                    .padding(.top, 24)

                // ご家族向け。高齢の方が迷わないよう、小さく目立たない形で置く
                NavigationLink(value: HomeDestination.page(.settings)) {
                    Text("ご家族の方へ: お勧めの設定")
                        .font(.footnote)
                        .underline()
                }
            }
            .padding(20)
        }
        .navigationTitle("使い方")
    }
}

#Preview {
    NavigationStack {
        HowToView()
    }
}
