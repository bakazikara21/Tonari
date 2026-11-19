// 画面内に見えている「操作できる要素」を集めて一覧にする処理。
// 「たすけて」ボタンが押されたときだけ呼ばれる。
// 入力欄の値(.value)の中身は使わない。空かどうか(入力済みかどうか)の判定にだけ使う。
(() => {
    "use strict";

    // 操作できる要素の候補
    const INTERACTIVE_SELECTOR = [
        "a[href]",
        "button",
        "input:not([type='hidden'])",
        "select",
        "textarea",
        "summary",
        "[role='button']",
        "[role='link']",
        "[role='checkbox']",
        "[role='radio']",
        "[contenteditable]:not([contenteditable='false'])",
    ].join(",");

    // ボタンとして扱う input の type
    const BUTTON_INPUT_TYPES = new Set(["submit", "button", "reset", "image"]);

    // パスワード・暗証番号・カード番号らしい入力欄を見分ける手がかり
    // (input の種類に加え、name / id / autocomplete / ラベルの文字に対して調べる)
    // server/safety.py の SENSITIVE_HINT と同じ内容に保つこと
    const SENSITIVE_HINT = /password|passwd|passcode|pass_code|(^|[^a-z])pwd([^a-z]|$)|パスワード|暗証|(^|[^a-z])pin([^a-z]|code|no|num|$)|card.?(num|no)|cc-?(num|no|csc|cvc|exp)|cvv|cvc|security.?code|セキュリティ.?コード|カード番号|one-time-code/i;

    const MAX_LABEL_LENGTH = 80;

    // 空白をまとめて、長すぎる文字は切る
    function normalize(text) {
        return (text || "").replace(/\s+/g, " ").trim().slice(0, MAX_LABEL_LENGTH);
    }

    // 要素の種類を決める
    function kindOf(el) {
        const tag = el.tagName.toLowerCase();
        if (tag === "a") return "link";
        if (tag === "button" || tag === "summary") return "button";
        if (tag === "select") return "select";
        if (tag === "textarea") return "textarea";
        if (tag === "input") {
            // el.type は属性を正規化したもので、入力された値ではない
            const type = el.type;
            if (type === "password") return "password";
            if (type === "checkbox") return "checkbox";
            if (type === "radio") return "radio";
            if (BUTTON_INPUT_TYPES.has(type)) return "button";
            if (type === "file") return "file";
            return "text-input";
        }
        const role = (el.getAttribute("role") || "").toLowerCase();
        if (["button", "link", "checkbox", "radio"].includes(role)) return role;
        if (el.isContentEditable) return "textarea";
        return "other";
    }

    // <label> の文字だけを取り出す(中にある入力欄・選択欄の中身は含めない)
    function labelElementText(label) {
        const copy = label.cloneNode(true);
        copy.querySelectorAll("input, select, textarea, [contenteditable]").forEach((node) => node.remove());
        return copy.textContent;
    }

    // 表示されている文字やラベルを決める。入力欄の値は読まない。
    function labelOf(el, kind, doc) {
        const labelledBy = el.getAttribute("aria-labelledby");
        if (labelledBy) {
            const text = labelledBy.split(/\s+/)
                .map((id) => doc.getElementById(id))
                .filter(Boolean)
                .map(labelElementText)
                .join(" ");
            if (normalize(text)) return normalize(text);
        }

        const ariaLabel = normalize(el.getAttribute("aria-label"));
        if (ariaLabel) return ariaLabel;

        // 入力欄・選択欄は、ひも付いた <label> を使う
        if (el.labels && el.labels.length > 0) {
            const text = normalize(Array.from(el.labels).map(labelElementText).join(" "));
            if (text) return text;
        }

        const tag = el.tagName.toLowerCase();
        if (tag === "input" && kind === "button") {
            // 送信ボタン等の value 属性はボタンに表示される文字で、利用者の入力ではない
            const text = normalize(el.getAttribute("value") || el.getAttribute("alt"));
            if (text) return text;
        }

        // リンクやボタンは中の文字を使う。編集できる欄(contenteditable)の中身は入力内容なので読まない。
        const isEditable = tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
        if (!isEditable) {
            const text = normalize(el.innerText);
            if (text) return text;
            const img = el.querySelector("img[alt]");
            if (img && normalize(img.getAttribute("alt"))) return normalize(img.getAttribute("alt"));
        }

        return normalize(el.getAttribute("placeholder") || el.getAttribute("title"));
    }

    // パスワード・暗証番号・カード番号の欄かどうか
    function isSensitiveField(el, kind, label) {
        if (kind === "password") return true;
        if (kind !== "text-input" && kind !== "textarea") return false;
        const hints = [
            el.getAttribute("name"),
            el.getAttribute("id"),
            el.getAttribute("autocomplete"),
            el.getAttribute("placeholder"),
            label,
        ];
        return hints.some((hint) => hint && SENSITIVE_HINT.test(hint));
    }

    // ---- 入力の状態(値そのものは扱わず、真偽値だけを返す) ----

    // 入力済みかどうか。値は空かどうかの判定にだけ使い、どこにも残さない。
    function isFilled(el) {
        if (el.isContentEditable && !("value" in el)) return el.textContent.trim() !== "";
        return el.value !== "";
    }

    // チェック済みかどうか(チェックボックス・ラジオボタン)
    function isChecked(el) {
        if (el.tagName.toLowerCase() === "input") return el.checked;
        return el.getAttribute("aria-checked") === "true";
    }

    // サイトが「入力に誤りがある」と示しているか
    function isInvalid(el) {
        if (el.getAttribute("aria-invalid") === "true") return true;
        try {
            return el.matches(":user-invalid");
        } catch (error) {
            return false; // :user-invalid に対応していない環境
        }
    }

    // 種類ごとに、一覧に加える状態を決める
    function stateOf(el, kind) {
        switch (kind) {
        case "password":
        case "secret":
            // 秘密の欄は「入力済みかどうか」だけ(誤りの印も含めない)
            return { filled: isFilled(el) };
        case "text-input":
        case "textarea":
        case "select":
            return { filled: isFilled(el), invalid: isInvalid(el) };
        case "checkbox":
        case "radio":
            return { checked: isChecked(el), invalid: isInvalid(el) };
        default:
            return {};
        }
    }

    // 押せない状態(無効化・inert)の要素は除く
    function isOperable(el) {
        if (el.disabled) return false;
        if (el.getAttribute("aria-disabled") === "true") return false;
        if (el.closest("[inert]")) return false;
        return true;
    }

    // 画面(表示領域)の中に実際に見えているか
    function isVisibleInViewport(el, win) {
        const rect = el.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return false;
        if (rect.bottom <= 0 || rect.right <= 0 || rect.top >= win.innerHeight || rect.left >= win.innerWidth) {
            return false;
        }
        if (typeof el.checkVisibility === "function") {
            if (!el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return false;
        } else {
            const style = win.getComputedStyle(el);
            if (style.display === "none" || style.visibility !== "visible" || Number(style.opacity) === 0) return false;
        }
        return true;
    }

    /**
     * 見えている操作できる要素を集める。
     * @returns {{ items: Array<{id:number, kind:string, label:string, rect:{x:number,y:number,width:number,height:number},
     *                          filled?:boolean, checked?:boolean, invalid?:boolean}>,
     *             elementById: Map<number, Element> }}
     *   items は background.js に渡す一覧(DOM を含まない普通のデータ)。
     *   elementById は枠を出すために、案内中だけ手元に持っておく対応表。
     */
    function collectVisibleElements(doc, win) {
        const items = [];
        const elementById = new Map();

        for (const el of doc.querySelectorAll(INTERACTIVE_SELECTOR)) {
            if (!isOperable(el) || !isVisibleInViewport(el, win)) continue;

            let kind = kindOf(el);
            let label = labelOf(el, kind, doc);

            // 秘密の欄は種類と入力済みかどうかだけを記録する(ラベルは残さない)
            if (isSensitiveField(el, kind, label)) {
                kind = kind === "password" ? "password" : "secret";
                label = "";
            }

            const rect = el.getBoundingClientRect();
            const id = items.length + 1;
            items.push({
                id,
                kind,
                label,
                rect: {
                    x: Math.round(rect.left),
                    y: Math.round(rect.top),
                    width: Math.round(rect.width),
                    height: Math.round(rect.height),
                },
                ...stateOf(el, kind),
            });
            elementById.set(id, el);
        }

        return { items, elementById };
    }

    globalThis.TonariCollector = { collectVisibleElements };
})();
