// Tonari の画面(ボタンや案内文)へのタッチ・クリックを、Web ページ側に伝えないための処理。
//
// 多くのサイトは「メニューの外が押されたらメニューを閉じる」処理を、document や window で
// touchstart / pointerdown / mousedown / click などを受けて行っている(捕捉フェーズのこともある)。
// Tonari のボタンを押しただけでメニューが閉じないよう、ページのどの処理よりも先に
// window の捕捉フェーズで受け取り、Tonari 宛てのものはそこで止める。
// そのため、このファイルはページのスクリプトより先に動く document_start で読み込む。
(() => {
    "use strict";

    if (globalThis.TonariShield) return;

    // 止めるイベントの種類
    const SHIELDED_EVENTS = [
        "touchstart", "touchmove", "touchend", "touchcancel",
        "pointerdown", "pointermove", "pointerup", "pointercancel",
        "mousedown", "mouseup", "click", "dblclick", "contextmenu",
    ];

    let shieldHost = null;     // Tonari の画面を入れている要素(Shadow DOM の外側)
    let onActivate = null;     // Tonari の画面がクリックされたときの処理

    function onEvent(event) {
        // 閉じた Shadow DOM の中で起きたイベントは、外からは host で起きたように見える
        if (!shieldHost || event.target !== shieldHost) return;

        // ページ側の処理には一切渡さない(既定の動作=スクロール等は止めない)
        event.stopImmediatePropagation();

        // Tonari のボタンにフォーカスが移ると、ページ側の入力欄やメニューのフォーカスが外れるので防ぐ
        if (event.type === "mousedown") event.preventDefault();

        // ここで止めたので Shadow DOM の中のボタンには届かない。代わりに登録された処理を呼ぶ。
        if (event.type === "click" && onActivate) onActivate(event);
    }

    for (const type of SHIELDED_EVENTS) {
        window.addEventListener(type, onEvent, { capture: true });
    }

    globalThis.TonariShield = {
        /**
         * @param host     Tonari の画面を入れている要素
         * @param activate Tonari の画面がクリックされたときに呼ばれる関数 (event) => void
         */
        attach(host, activate) {
            shieldHost = host;
            onActivate = activate;
        },
    };
})();
