// 案内(案内文と押す要素の番号)を中継サーバーから受け取る処理。
// 呼び出し側(background.js)は requestGuide の形だけに依存する。
//
// 中継サーバーとの通信は、拡張機能のネイティブ側(SafariWebExtensionHandler.swift)が行う。
// 接続先はアプリと共通の Shared/ServerConfig.swift だけで決める(ここには書かない)。

// いまは目的を固定にしている
const GOAL = "このサイトの会員登録を完了する";

// ネイティブ側が受け付ける依頼の種類(SafariWebExtensionHandler.guideMessageType と同じ)
const MESSAGE_TYPE = "tonari:guide";

/**
 * @param items    画面内の操作できる要素の一覧
 * @param helpType 選ばれた困りごとの id("next-step" など。サーバー側で決まった質問文に置き換える)
 * @returns {Promise<{ message: string, targetId: number | null }>}
 *   通信に失敗したときは例外を投げる(待ち時間の上限はネイティブ側で 20 秒)
 */
export async function requestGuide(items, helpType) {
    // Safari では1つめの引数(アプリの ID)は使われず、この拡張機能を含むアプリに届く
    const reply = await browser.runtime.sendNativeMessage("application.id", {
        type: MESSAGE_TYPE,
        body: { goal: GOAL, helpType, items },
    });
    if (!reply || reply.ok !== true) {
        throw new Error(`中継サーバーから案内を受け取れませんでした: ${reply?.error ?? "応答なし"}`);
    }
    // 中身の検査は content.js 側(validator.js)で行う
    return reply.guide;
}
