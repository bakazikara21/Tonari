"""安全のための判別処理(拡張機能側の JS と同じ判別をサーバーでも行う)。

- 秘密の欄(パスワード・暗証番号・カード番号): collector.js の SENSITIVE_HINT と同じ内容に保つこと
- 確定のボタン: validator.js の COMMIT_ACTION_PATTERN と同じ内容に保つこと
- 偽の警告・詐欺: danger-check.js の SCAM_PATTERNS と同じ内容に保つこと
"""

import re

SECRET_KINDS = {"password", "secret"}

SENSITIVE_HINT = re.compile(
    r"password|passwd|passcode|pass_code|(^|[^a-z])pwd([^a-z]|$)|パスワード|暗証|"
    r"(^|[^a-z])pin([^a-z]|code|no|num|$)|card.?(num|no)|cc-?(num|no|csc|cvc|exp)|cvv|cvc|"
    r"security.?code|セキュリティ.?コード|カード番号|one-time-code",
    re.IGNORECASE,
)

COMMIT_ACTION_PATTERN = re.compile(
    r"購入|注文|契約|申し?込|支払|決済|確定|\b(purchase|buy|order|checkout|check out|subscribe|pay)\b",
    re.IGNORECASE,
)

SCAM_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    # ウイルス感染・故障をうたう偽の警告
    r"ウイルス.{0,15}(感染|検出|見つか|発見)",
    r"(iPhone|アイフォン|スマホ|スマートフォン|携帯|端末|デバイス).{0,15}(感染|破損|損傷|ハッキング|乗っ取)",
    r"(感染|ハッキング|乗っ取)されてい",
    # 電話・操作を急がせる
    r"今すぐ.{0,10}(電話|お電話|ご連絡|削除|駆除|修復|スキャン|インストール)",
    r"(サポート|サポートセンター|窓口).{0,10}(今すぐ|至急|すぐに).{0,10}(電話|連絡)",
    r"(残り|あと)\s*\d+\s*(秒|分).{0,20}(削除|消去|失われ|停止|ロック)",
    # 当選・プレゼント
    r"(当選|当せん)(しました|されました|者に選ばれ)",
    r"おめでとうございます.{0,30}(当選|選ばれ|プレゼント)",
    # アカウント停止をうたうフィッシング
    r"アカウント.{0,10}(停止|凍結|ロック|利用制限)(され|しました|いたしました)",
    # ギフトカードでの支払いを求める
    r"(ギフトカード|ギフト券|プリペイドカード|電子マネー).{0,20}(購入|支払|番号を)",
    # 英語の偽警告
    r"virus(es)?.{0,20}(detected|found|infected)",
    r"your (iphone|device|phone).{0,20}(infected|hacked|damaged|compromised)",
    r"call.{0,10}(apple|microsoft)?.{0,10}support.{0,10}(now|immediately)",
    r"(you('ve| have) won|congratulations.{0,30}winner)",
]]


def is_secret_label(label: str) -> bool:
    """ラベルが秘密の欄らしいか"""
    return bool(SENSITIVE_HINT.search(label))


def is_commit_action(kind: str, label: str) -> bool:
    """購入・契約・申込みなどを確定するボタン・リンクらしいか"""
    return kind in {"button", "link"} and bool(COMMIT_ACTION_PATTERN.search(label))


def looks_like_scam(text: str) -> bool:
    """文字が偽の警告・詐欺らしいか"""
    normalized = re.sub(r"\s+", " ", text)
    return any(pattern.search(normalized) for pattern in SCAM_PATTERNS)
