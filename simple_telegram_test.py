"""
簡單的 Telegram 測試腳本

此腳本會直接測試 Telegram Bot 是否能發送訊息。
"""
import os
from datetime import datetime


def main():
    print("=" * 80)
    print("Telegram 環境變數檢查")
    print("=" * 80)

    # Check environment variables
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    notifications_enabled = os.getenv("ENABLE_TELEGRAM_NOTIFICATIONS", "true")

    print(f"\n1. TELEGRAM_BOT_TOKEN: {'已設置 ✓' if bot_token else '未設置 ✗'}")
    if bot_token:
        print(f"   長度: {len(bot_token)} 字符")
        # Show first and last few characters for verification
        if len(bot_token) > 20:
            print(f"   格式: {bot_token[:8]}...{bot_token[-8:]}")

    print(f"\n2. TELEGRAM_CHAT_ID: {'已設置 ✓' if chat_id else '未設置 ✗'}")
    if chat_id:
        print(f"   值: {chat_id}")

    print(f"\n3. ENABLE_TELEGRAM_NOTIFICATIONS: {notifications_enabled}")
    if notifications_enabled.lower() == "true":
        print("   狀態: 已啟用 ✓")
    else:
        print("   狀態: 已停用 ✗")
        print("   ⚠️  警告: 通知功能已關閉!")

    # Summary
    print("\n" + "=" * 80)
    print("診斷結果")
    print("=" * 80)

    if not bot_token or not chat_id:
        print("\n❌ 缺少必要的環境變數")
        print("\n請在 Railway 設置以下環境變數:")
        print("1. TELEGRAM_BOT_TOKEN")
        print("2. TELEGRAM_CHAT_ID")
        print("\n設置方法:")
        print("- 打開 Railway 專案")
        print("- 點擊服務 > Variables 標籤")
        print("- 添加環境變數")
        print("- 重新部署服務")
        return False

    if notifications_enabled.lower() != "true":
        print("\n❌ Telegram 通知已停用")
        print("\n請將 ENABLE_TELEGRAM_NOTIFICATIONS 設為 'true'")
        return False

    print("\n✓ 環境變數檢查通過")

    # Try to send a test message
    print("\n正在嘗試發送測試訊息...")
    try:
        from x_auto.notifications.telegram_bot import send_telegram_message

        test_message = (
            "🧪 *測試訊息*\n\n"
            f"發送時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "如果您看到這條訊息，表示 Telegram Bot 運作正常！"
        )

        success = send_telegram_message(test_message)

        if success:
            print("✓ 測試訊息發送成功!")
            print("  請檢查您的 Telegram 是否收到訊息")
            return True
        else:
            print("✗ 測試訊息發送失敗")
            print("  請查看上方的錯誤日誌")
            return False

    except Exception as e:
        print(f"✗ 發送測試訊息時發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
