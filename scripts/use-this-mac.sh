#!/bin/sh
# 実機の iPhone から、この Mac の中継サーバーにつなぐための設定ファイルを作る。
# Mac の名前(○○.local)を調べて Shared/LocalServer.plist に書く。このファイルは Git に入れない。
# シミュレータはこのファイルを使わず、いつも http://localhost:8000 につなぐ。
set -eu

cd "$(dirname "$0")/.."

# 「システム設定」→「一般」→「共有」の「ローカルホスト名」と同じもの(英数字とハイフンだけ)
host="$(scutil --get LocalHostName)"
url="http://${host}.local:8000"

cat > Shared/LocalServer.plist <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>ServerURL</key>
	<string>${url}</string>
</dict>
</plist>
PLIST

echo "Shared/LocalServer.plist を作りました: ${url}"
echo "Xcode でアプリをビルドし直してください。"
