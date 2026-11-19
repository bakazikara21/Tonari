// 案内(案内文と押す要素の番号)を中継サーバーから受け取る処理。
// 呼び出し側(background.js)は requestGuide の形だけに依存する。

// 中継サーバーの URL。変更するときはここだけを書き換える。
// (別のホストに変える場合は、manifest.json の host_permissions にもそのホストを足す)
const SERVER_URL = "http://localhost:8000/guide";

// いまは目的を固定にしている
const GOAL = "このサイトの会員登録を完了する";

// サーバーが応答しないときに待つ時間(ミリ秒)
const TIMEOUT_MS = 20000;

/**
 * @param items    画面内の操作できる要素の一覧
 * @param helpType 選ばれた困りごとの id("next-step" など。サーバー側で決まった質問文に置き換える)
 * @returns {Promise<{ message: string, targetId: number | null }>}
 *   通信に失敗したときは例外を投げる
 */
export async function requestGuide(items, helpType) {
    const response = await fetch(SERVER_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal: GOAL, helpType, items }),
        signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!response.ok) {
        throw new Error(`中継サーバーがエラーを返しました: ${response.status}`);
    }
    // 中身の検査は content.js 側(validator.js)で行う
    return response.json();
}
