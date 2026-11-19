// 偽の警告や詐欺が疑われる画面かどうかを、画面の文字から判別する処理。
// 判別は端末の中だけで行い、画面の文字はサーバーに送らない。
// 疑わしいときは操作を案内せず、「ご家族に相談してください」と表示する。
(() => {
    "use strict";

    // 偽の警告・詐欺によく出る言い回し
    // server/safety.py の SCAM_PATTERNS と同じ内容に保つこと
    const SCAM_PATTERNS = [
        // ウイルス感染・故障をうたう偽の警告
        /ウイルス.{0,15}(感染|検出|見つか|発見)/,
        /(iPhone|アイフォン|スマホ|スマートフォン|携帯|端末|デバイス).{0,15}(感染|破損|損傷|ハッキング|乗っ取)/i,
        /(感染|ハッキング|乗っ取)されてい/,
        // 電話・操作を急がせる
        /今すぐ.{0,10}(電話|お電話|ご連絡|削除|駆除|修復|スキャン|インストール)/,
        /(サポート|サポートセンター|窓口).{0,10}(今すぐ|至急|すぐに).{0,10}(電話|連絡)/,
        /(残り|あと)\s*\d+\s*(秒|分).{0,20}(削除|消去|失われ|停止|ロック)/,
        // 当選・プレゼント
        /(当選|当せん)(しました|されました|者に選ばれ)/,
        /おめでとうございます.{0,30}(当選|選ばれ|プレゼント)/,
        // アカウント停止をうたうフィッシング
        /アカウント.{0,10}(停止|凍結|ロック|利用制限)(され|しました|いたしました)/,
        // ギフトカードでの支払いを求める
        /(ギフトカード|ギフト券|プリペイドカード|電子マネー).{0,20}(購入|支払|番号を)/,
        // 英語の偽警告
        /virus(es)?.{0,20}(detected|found|infected)/i,
        /your (iphone|device|phone).{0,20}(infected|hacked|damaged|compromised)/i,
        /call.{0,10}(apple|microsoft)?.{0,10}support.{0,10}(now|immediately)/i,
        /(you('ve| have) won|congratulations.{0,30}winner)/i,
    ];

    // 判別に使う文字の上限(長すぎるページは先頭だけ見る)
    const MAX_TEXT_LENGTH = 20000;

    /** 文字が詐欺・偽の警告らしいか */
    function looksLikeScam(text) {
        const normalized = (text || "").replace(/\s+/g, " ").slice(0, MAX_TEXT_LENGTH);
        return SCAM_PATTERNS.some((pattern) => pattern.test(normalized));
    }

    /** 画面のタイトルと表示されている文字を取り出す(入力欄の値は innerText に含まれない) */
    function pageText(doc) {
        const body = doc.body ? doc.body.innerText : "";
        return `${doc.title || ""}\n${body}`;
    }

    globalThis.TonariDangerCheck = { looksLikeScam, pageText };
})();
