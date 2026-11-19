// Web ページに「たすけて」ボタンを出し、案内(枠と案内文)を表示する。
// 拡張機能はクリックや入力を代行しない。枠は見せるだけで、操作は本人が行う。
// ページを読み取るのは「たすけて」が押されてから「とじる」が押されるまでだけ。
(() => {
    "use strict";

    // 同じページで二重に動かない
    if (globalThis.__tonariContentLoaded) return;
    globalThis.__tonariContentLoaded = true;

    const { collectVisibleElements } = globalThis.TonariCollector;
    const { validateGuide } = globalThis.TonariValidator;
    const { looksLikeScam, pageText } = globalThis.TonariDangerCheck;

    // 検査に通らなかったときなどに出す決まった文
    const FALLBACK_MESSAGE = "うまく案内できませんでした。もう一度「たすけて」を押してください。";
    const UNAVAILABLE_MESSAGE = "いまは案内できません。";
    const COMMIT_MESSAGE = "ここから先はご自身で内容を確かめてください。";
    const FAMILY_MESSAGE = "この画面は、だましの画面かもしれません。操作をやめて、ご家族に相談してください。";

    // 最初に一度だけ出す注意。同意したことは storage に記録する。
    const NOTICE_MESSAGE = "「たすけて」を押すと、いま見ている画面のボタンや入力欄の名前と、入力がすんでいるかどうかが、案内を作るために AI(Google の Gemini)に送られます。入力した内容や、パスワード・暗証番号・カード番号そのものは送りません。";
    // 送る内容を変えたら、キーを変えて注意をもう一度出す
    const NOTICE_ACCEPTED_KEY = "noticeAcceptedV2";

    // 「たすけて」を押したときに選べる、よくある困りごと。
    // id はサーバー(server/main.py の HELP_QUESTIONS)と同じものを使う。
    const HELP_OPTIONS = [
        { id: "next-step", label: "つぎに何をすればいい?" },
        { id: "what-screen", label: "この画面は何の画面?" },
        { id: "signup", label: "会員登録がしたい" },
    ];

    // 画面の見た目。ページの CSS の影響を受けないよう Shadow DOM の中に置く。
    const STYLE = `
        :host { all: initial; }
        * { box-sizing: border-box; font-family: -apple-system, "Hiragino Sans", sans-serif; -webkit-text-size-adjust: none; }
        [hidden] { display: none !important; }
        .help {
            position: fixed;
            right: 16px;
            bottom: calc(16px + env(safe-area-inset-bottom));
            min-width: 140px;
            min-height: 76px;
            padding: 12px 24px;
            border: 3px solid #fff;
            border-radius: 38px;
            background: #C2410C;
            color: #fff;
            font-size: 30px;
            font-weight: bold;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
            z-index: 2147483647;
        }
        .help:disabled { background: #6B7280; }
        .frame {
            position: fixed;
            border: 6px solid #FF6B00;
            border-radius: 10px;
            box-shadow: 0 0 0 4px #fff, 0 0 18px 6px rgba(0, 0, 0, 0.45);
            /* 枠の上から下の要素をそのまま押せるようにする */
            pointer-events: none;
            z-index: 2147483646;
        }
        .panel {
            position: fixed;
            left: 0;
            right: 0;
            bottom: 0;
            padding: 20px 20px calc(20px + env(safe-area-inset-bottom));
            border-top: 6px solid #FF6B00;
            background: #fff;
            color: #111;
            box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.3);
            z-index: 2147483647;
        }
        .message {
            margin: 0 0 16px;
            font-size: 26px;
            line-height: 1.5;
            font-weight: bold;
        }
        .buttons {
            display: flex;
            gap: 12px;
        }
        .buttons button {
            flex: 1;
            min-height: 64px;
            border: none;
            border-radius: 14px;
            background: #1F2937;
            color: #fff;
            font-size: 26px;
            font-weight: bold;
        }
        .buttons .secondary {
            background: #fff;
            color: #1F2937;
            border: 3px solid #1F2937;
        }
        .menu-title {
            margin: 0 0 16px;
            font-size: 26px;
            font-weight: bold;
        }
        .choices {
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-bottom: 12px;
        }
        .choices button {
            min-height: 64px;
            padding: 10px 16px;
            border: 3px solid #C2410C;
            border-radius: 14px;
            background: #FFF7ED;
            color: #111;
            font-size: 24px;
            font-weight: bold;
            text-align: left;
        }
        .notice-text {
            margin: 0 0 16px;
            font-size: 22px;
            line-height: 1.5;
        }
    `;

    const host = document.createElement("div");
    host.style.cssText = "position: fixed; top: 0; left: 0; width: 0; height: 0; z-index: 2147483647;";
    const root = host.attachShadow({ mode: "closed" });
    root.innerHTML = `
        <style>${STYLE}</style>
        <button class="help" type="button">たすけて</button>
        <div class="frame" hidden></div>
        <div class="panel" hidden aria-live="polite">
            <p class="message"></p>
            <div class="buttons">
                <button class="replay secondary" type="button">もう一度きく</button>
                <button class="close" type="button">とじる</button>
            </div>
        </div>
        <div class="panel menu" hidden role="dialog" aria-label="こまっていること">
            <p class="menu-title">どんなことで こまっていますか?</p>
            <div class="choices"></div>
            <div class="buttons">
                <button class="menu-cancel secondary" type="button">やめる</button>
            </div>
        </div>
        <div class="panel notice" hidden role="dialog" aria-label="ご注意">
            <p class="notice-text"></p>
            <div class="buttons">
                <button class="decline secondary" type="button">やめる</button>
                <button class="accept" type="button">わかりました</button>
            </div>
        </div>
    `;
    document.documentElement.appendChild(host);

    const helpButton = root.querySelector(".help");
    const frame = root.querySelector(".frame");
    const panel = root.querySelector(".panel:not(.notice):not(.menu)");
    const messageText = root.querySelector(".message");
    const replayButton = root.querySelector(".replay");
    const closeButton = root.querySelector(".close");
    const notice = root.querySelector(".notice");
    const acceptButton = root.querySelector(".accept");
    const declineButton = root.querySelector(".decline");
    root.querySelector(".notice-text").textContent = NOTICE_MESSAGE;
    const menu = root.querySelector(".menu");
    const choices = root.querySelector(".choices");
    const menuCancelButton = root.querySelector(".menu-cancel");

    // 案内中だけ持つ状態。案内が終わったら null に戻し、要素への参照を手放す。
    let guide = null; // { element: Element | null }
    let framePending = false;

    // 新しい画面(注意・困りごと・案内文)を出した直後のタップは無視する。
    // 「たすけて」を2回続けて押すと、2回めが同じ位置に出た「やめる」「わかりました」に当たり、
    // メニューがすぐ閉じて「押しても反応しない」ように見えたり、注意に意図せず同意したりするため。
    const TAP_GUARD_MS = 1000;
    let ignoreTapsUntil = 0;

    function guardTaps() {
        ignoreTapsUntil = performance.now() + TAP_GUARD_MS;
    }

    // 枠を対象の要素の位置に合わせる(スクロール中も追いかける)
    function placeFrame() {
        framePending = false;
        const element = guide && guide.element;
        if (!element || !element.isConnected) {
            frame.hidden = true;
            return;
        }
        const rect = element.getBoundingClientRect();
        // 要素との隙間 6px + 枠の太さ 6px だけ外側に広げる
        const offset = 12;
        frame.style.left = `${rect.left - offset}px`;
        frame.style.top = `${rect.top - offset}px`;
        frame.style.width = `${rect.width + offset * 2}px`;
        frame.style.height = `${rect.height + offset * 2}px`;
        frame.hidden = false;
    }

    function schedulePlaceFrame() {
        if (framePending) return;
        framePending = true;
        requestAnimationFrame(placeFrame);
    }

    // 対象の要素が案内文に隠れる場合は、見える位置までページをずらす(表示の補助だけ)
    function revealAbovePanel(element) {
        const panelTop = panel.getBoundingClientRect().top;
        const rect = element.getBoundingClientRect();
        if (rect.bottom > panelTop) {
            window.scrollBy({ top: rect.bottom - panelTop + 24, behavior: "smooth" });
        }
    }

    // ---- 読み上げ ----

    // iOS では、ボタンを押した直後でないと読み上げが始まらないことがある。
    // そのため押した時点で空の読み上げを一度行い、後から案内文を読めるようにしておく。
    function unlockSpeech() {
        if (!("speechSynthesis" in window)) return;
        speechSynthesis.speak(new SpeechSynthesisUtterance(""));
    }

    function speak(text) {
        if (!("speechSynthesis" in window)) return;
        speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "ja-JP";
        utterance.rate = 0.9; // 少しゆっくり
        speechSynthesis.speak(utterance);
    }

    function stopSpeaking() {
        if ("speechSynthesis" in window) speechSynthesis.cancel();
    }

    // ---- 案内の表示 ----

    function showGuide(message, element) {
        guide = { element, message };
        messageText.textContent = message; // 文字として入れる(HTML として解釈しない)
        helpButton.hidden = true;
        panel.hidden = false;
        guardTaps();
        speak(message);
        if (element) {
            placeFrame();
            revealAbovePanel(element);
            window.addEventListener("scroll", schedulePlaceFrame, { capture: true, passive: true });
            window.addEventListener("resize", schedulePlaceFrame, { passive: true });
        }
    }

    // 案内を終える。枠と案内文を消し、ページの読み取りもここで終わる。
    function closeGuide() {
        stopSpeaking();
        window.removeEventListener("scroll", schedulePlaceFrame, { capture: true });
        window.removeEventListener("resize", schedulePlaceFrame);
        guide = null;
        frame.hidden = true;
        panel.hidden = true;
        messageText.textContent = "";
        helpButton.hidden = false;
    }

    /** @param helpType 選ばれた困りごとの id(HELP_OPTIONS) */
    async function startGuide(helpType) {
        helpButton.disabled = true;
        try {
            // 偽の警告・詐欺が疑われる画面では、何も送らずに相談を促す(判別は端末の中だけで行う)
            if (looksLikeScam(pageText(document))) {
                showGuide(FAMILY_MESSAGE, null);
                return;
            }

            const { items, elementById } = collectVisibleElements(document, window);
            const response = await browser.runtime.sendMessage({ type: "tonari:requestGuide", items, helpType });

            // 中継サーバーとの通信に失敗した
            if (response && response.unavailable) {
                showGuide(UNAVAILABLE_MESSAGE, null);
                return;
            }

            // 応答をそのまま信じず、番号が実在するかなどを検査する
            const result = validateGuide(response, items);
            if (result.ok) {
                const element = result.target ? elementById.get(result.target.id) : null;
                showGuide(result.message, element || null);
            } else if (result.reason === "scam") {
                showGuide(FAMILY_MESSAGE, null);
            } else if (result.reason === "commit-action") {
                showGuide(COMMIT_MESSAGE, null);
            } else {
                showGuide(FALLBACK_MESSAGE, null);
            }
        } catch (error) {
            console.error("Tonari: 案内の取得に失敗しました", error);
            showGuide(UNAVAILABLE_MESSAGE, null);
        } finally {
            helpButton.disabled = false;
        }
    }

    // ---- 最初の注意 ----

    async function isNoticeAccepted() {
        try {
            const stored = await browser.storage.local.get(NOTICE_ACCEPTED_KEY);
            return stored[NOTICE_ACCEPTED_KEY] === true;
        } catch (error) {
            return false; // 読めないときは、もう一度注意を出す
        }
    }

    async function onHelpPressed() {
        if (await isNoticeAccepted()) {
            showMenu();
            return;
        }
        // まだ同意していなければ、画面の内容を読む前に注意を出す
        helpButton.hidden = true;
        notice.hidden = false;
        guardTaps();
    }

    async function acceptNotice() {
        notice.hidden = true;
        try {
            await browser.storage.local.set({ [NOTICE_ACCEPTED_KEY]: true });
        } catch (error) {
            console.error("Tonari: 同意を記録できませんでした", error);
        }
        showMenu();
    }

    function declineNotice() {
        notice.hidden = true;
        helpButton.hidden = false;
    }

    // ---- 困りごとの選択 ----
    // 選ばれるまではページを読まず、AI にも何も送らない。

    function showMenu() {
        helpButton.hidden = true;
        menu.hidden = false;
        guardTaps();
    }

    function hideMenu() {
        menu.hidden = true;
        helpButton.hidden = false;
    }

    function chooseHelp(helpType) {
        hideMenu();
        startGuide(helpType);
    }

    // ---- ボタンの操作 ----
    // ページ側にタップが伝わらないよう、イベントは shield.js が window で止める。
    // そのため各ボタンの処理はここに登録しておき、押された位置のボタンを探して呼ぶ。
    const tapHandlers = new Map();

    function onTap(button, handler) {
        tapHandlers.set(button, handler);
    }

    globalThis.TonariShield.attach(host, (event) => {
        const hit = root.elementFromPoint(event.clientX, event.clientY);
        const button = hit && hit.closest("button");
        if (!button || button.disabled) return;
        if (performance.now() < ignoreTapsUntil) return;
        const handler = tapHandlers.get(button);
        if (handler) handler();
    });

    for (const option of HELP_OPTIONS) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = option.label;
        choices.appendChild(button);
        onTap(button, () => {
            unlockSpeech();
            chooseHelp(option.id);
        });
    }
    onTap(menuCancelButton, hideMenu);

    onTap(helpButton, () => {
        unlockSpeech();
        onHelpPressed();
    });
    onTap(acceptButton, () => {
        unlockSpeech();
        acceptNotice();
    });
    onTap(declineButton, declineNotice);
    onTap(replayButton, () => {
        if (guide) speak(guide.message);
    });
    onTap(closeButton, closeGuide);
})();
