// content.js から要素の一覧を受け取り、案内を返す中継役。
// 案内の取得は guide-provider.js に分けてある。
import { requestGuide } from "./guide-provider.js";

browser.runtime.onMessage.addListener((request) => {
    // Tonari の案内依頼以外は扱わない
    if (!request || request.type !== "tonari:requestGuide") return;
    if (!Array.isArray(request.items)) {
        return Promise.resolve({ unavailable: true });
    }
    // 通信に失敗したときは「案内できない」ことだけを伝える
    return requestGuide(request.items, request.helpType).catch((error) => {
        console.error("Tonari: 案内の取得に失敗しました", error);
        return { unavailable: true };
    });
});
