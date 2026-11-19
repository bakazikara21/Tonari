// 中継サーバーから届いた案内の応答(AI の応答)をコードで検査する処理。
// 検査に通らない応答では枠を出さない。
(() => {
    "use strict";

    const MAX_MESSAGE_LENGTH = 200;

    // 購入・契約・申込みなどを確定するボタンらしい文字
    // server/safety.py の COMMIT_ACTION_PATTERN と同じ内容に保つこと
    const COMMIT_ACTION_PATTERN = /購入|注文|契約|申し?込|支払|決済|確定|\b(purchase|buy|order|checkout|check out|subscribe|pay)\b/i;

    // ボタン・リンクのうち、確定の操作らしいものか
    function isCommitAction(item) {
        if (item.kind !== "button" && item.kind !== "link") return false;
        return COMMIT_ACTION_PATTERN.test(item.label || "");
    }

    function fail(reason) {
        return { ok: false, reason };
    }

    /**
     * 応答を検査する。
     * @param response 応答 { message: string, targetId: number | null, warning?: "scam" | "commit-action" | null }
     * @param items    collectVisibleElements で集めた一覧
     * @returns 成功時 { ok: true, message, target }(target は一覧の要素、または null)
     *          失敗時 { ok: false, reason }
     */
    function validateGuide(response, items) {
        if (!Array.isArray(items)) return fail("no-items");
        if (!response || typeof response !== "object") return fail("not-object");

        // サーバーが判定した警告を優先する(枠は出さない)
        if (response.warning === "scam") return fail("scam");
        if (response.warning === "commit-action") return fail("commit-action");

        const { message, targetId } = response;
        if (typeof message !== "string" || message.trim() === "") return fail("no-message");
        if (message.length > MAX_MESSAGE_LENGTH) return fail("message-too-long");

        // 押す場所がない案内(文だけ)は認める
        if (targetId === null || targetId === undefined) {
            return { ok: true, message: message.trim(), target: null };
        }

        // 番号は整数で、一覧に実在すること
        if (!Number.isInteger(targetId)) return fail("invalid-target-id");
        const target = items.find((item) => item.id === targetId);
        if (!target) return fail("unknown-target-id");

        // 確定のボタンには枠を出さない
        if (isCommitAction(target)) return fail("commit-action");

        return { ok: true, message: message.trim(), target };
    }

    globalThis.TonariValidator = { validateGuide, isCommitAction };
})();
