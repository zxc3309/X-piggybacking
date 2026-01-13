"""
Telegram 通知診斷工具

此腳本會檢查 Telegram 通知功能為何沒有發送訊息。
"""
import os
import sys
import logging
from datetime import datetime
import pytz

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_environment_variables():
    """檢查環境變數是否正確設置"""
    print("\n" + "=" * 80)
    print("🔍 步驟 1: 檢查環境變數")
    print("=" * 80)

    issues = []

    # Check Telegram credentials
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    notifications_enabled = os.getenv("ENABLE_TELEGRAM_NOTIFICATIONS", "true")

    print(f"TELEGRAM_BOT_TOKEN: {'✅ 已設置' if bot_token else '❌ 未設置'}")
    if bot_token:
        print(f"  Token 長度: {len(bot_token)} 字符")
        print(f"  Token 前綴: {bot_token[:10]}...")
    else:
        issues.append("TELEGRAM_BOT_TOKEN 未設置")

    print(f"TELEGRAM_CHAT_ID: {'✅ 已設置' if chat_id else '❌ 未設置'}")
    if chat_id:
        print(f"  Chat ID: {chat_id}")
    else:
        issues.append("TELEGRAM_CHAT_ID 未設置")

    print(f"ENABLE_TELEGRAM_NOTIFICATIONS: {notifications_enabled}")
    if notifications_enabled.lower() != "true":
        issues.append(f"ENABLE_TELEGRAM_NOTIFICATIONS 設為 '{notifications_enabled}' (應該是 'true')")
    else:
        print("  ✅ Telegram 通知已啟用")

    # Check other relevant variables
    print("\n其他相關設置:")
    print(f"OPENAI_API_KEY: {'✅ 已設置' if os.getenv('OPENAI_API_KEY') else '❌ 未設置'}")
    print(f"APIFY_TOKEN: {'✅ 已設置' if os.getenv('APIFY_TOKEN') else '❌ 未設置'}")
    print(f"GOOGLE_SHEET_ID: {'✅ 已設置' if os.getenv('GOOGLE_SHEET_ID') else '❌ 未設置'}")

    return issues, bot_token, chat_id


def test_telegram_connection(bot_token, chat_id):
    """測試 Telegram 連接"""
    print("\n" + "=" * 80)
    print("🔍 步驟 2: 測試 Telegram 連接")
    print("=" * 80)

    if not bot_token or not chat_id:
        print("❌ 跳過連接測試 (缺少憑證)")
        return False

    try:
        from telegram import Bot
        from telegram.error import TelegramError, Unauthorized, NetworkError

        print("正在測試 Bot Token...")
        bot = Bot(token=bot_token)

        # Test bot info
        try:
            bot_info = bot.get_me()
            print(f"✅ Bot 連接成功!")
            print(f"  Bot 名稱: @{bot_info.username}")
            print(f"  Bot ID: {bot_info.id}")
        except Unauthorized as e:
            print(f"❌ Bot Token 無效或未授權: {e}")
            return False
        except NetworkError as e:
            print(f"❌ 網絡錯誤: {e}")
            return False
        except TelegramError as e:
            print(f"❌ Telegram API 錯誤: {e}")
            return False

        # Test sending message
        print(f"\n正在發送測試訊息到 Chat ID: {chat_id}...")
        test_message = (
            f"🧪 *Telegram 診斷測試*\n\n"
            f"這是一條測試訊息\n"
            f"時間: {datetime.now(pytz.timezone('Asia/Taipei')).strftime('%Y-%m-%d %H:%M:%S')} (Asia/Taipei)\n\n"
            f"如果您看到這條訊息，表示 Telegram 通知功能正常運作！"
        )

        try:
            bot.send_message(
                chat_id=chat_id,
                text=test_message,
                parse_mode='Markdown'
            )
            print("✅ 測試訊息發送成功!")
            print("   請檢查您的 Telegram 是否收到訊息")
            return True
        except TelegramError as e:
            print(f"❌ 發送訊息失敗: {e}")
            print("   可能的原因:")
            print("   1. Chat ID 不正確")
            print("   2. Bot 尚未被加入該聊天")
            print("   3. Bot 沒有發送訊息的權限")
            return False

    except ImportError:
        print("❌ 無法導入 python-telegram-bot 套件")
        print("   請執行: pip install python-telegram-bot>=22.5,<23.0")
        return False
    except Exception as e:
        print(f"❌ 未預期的錯誤: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_google_sheets():
    """檢查 Google Sheets 中的數據"""
    print("\n" + "=" * 80)
    print("🔍 步驟 3: 檢查 Google Sheets 數據")
    print("=" * 80)

    try:
        from x_auto.integrations.google_sheets import get_worksheet_data

        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        if not sheet_id:
            print("❌ GOOGLE_SHEET_ID 未設置，無法檢查 Google Sheets")
            return

        # Check scraped output
        output_ws_name = os.getenv("GOOGLE_WS_SCRAPED_OUTPUT", "scraped_output")
        print(f"正在檢查工作表: {output_ws_name}")

        try:
            data = get_worksheet_data(sheet_id, output_ws_name)
            if data and len(data) > 1:  # More than just header
                print(f"✅ 找到 {len(data) - 1} 行數據")

                # Check recent posts
                print("\n最近的貼文:")
                headers = data[0] if data else []

                # Find relevant column indices
                try:
                    timestamp_idx = headers.index('Timestamp') if 'Timestamp' in headers else None
                    summary_idx = headers.index('Summary') if 'Summary' in headers else None
                    category_idx = headers.index('Category') if 'Category' in headers else None
                except ValueError:
                    timestamp_idx = summary_idx = category_idx = None

                # Show last 5 posts
                recent_posts = data[1:6] if len(data) > 1 else []
                for i, row in enumerate(recent_posts, 1):
                    print(f"\n  貼文 {i}:")
                    if timestamp_idx and len(row) > timestamp_idx:
                        print(f"    時間: {row[timestamp_idx]}")
                    if summary_idx and len(row) > summary_idx:
                        print(f"    摘要: {row[summary_idx][:80]}...")
                    if category_idx and len(row) > category_idx:
                        print(f"    類別: {row[category_idx]}")

                # Check if any posts have summary and category (meaning they were valuable)
                if summary_idx and category_idx:
                    valuable_posts = [
                        row for row in data[1:]
                        if len(row) > max(summary_idx, category_idx) and
                           row[summary_idx] and row[category_idx]
                    ]
                    print(f"\n📊 有價值的貼文數量: {len(valuable_posts)}")

                    if valuable_posts:
                        print("✅ 發現有價值的貼文，但沒有發送到 Telegram")
                        print("   這確認了問題在於 Telegram 發送環節")
                    else:
                        print("⚠️  沒有找到有 Summary 和 Category 的貼文")
                        print("   這表示 LLM 可能沒有判斷任何貼文為有價值")
            else:
                print("❌ 工作表中沒有數據")
        except Exception as e:
            print(f"❌ 讀取工作表失敗: {e}")
            import traceback
            traceback.print_exc()

    except ImportError as e:
        print(f"❌ 無法導入必要的模組: {e}")
    except Exception as e:
        print(f"❌ 檢查 Google Sheets 時發生錯誤: {e}")
        import traceback
        traceback.print_exc()


def check_recent_logs():
    """檢查最近的執行日誌"""
    print("\n" + "=" * 80)
    print("🔍 步驟 4: 建議檢查 Railway 日誌")
    print("=" * 80)

    print("\n在 Railway 上查看日誌:")
    print("1. 訪問 Railway 專案控制台")
    print("2. 點擊您的服務")
    print("3. 查看 'Deployments' 或 'Logs' 標籤")
    print("4. 搜尋以下關鍵字:")
    print("   - '[Telegram]' - 查看 Telegram 相關日誌")
    print("   - 'RuntimeError' - 查看是否有配置錯誤")
    print("   - 'Sending daily summary' - 查看是否嘗試發送")
    print("   - 'matched posts' - 查看有多少貼文匹配")
    print("   - 'Unauthorized' - 查看 Token 是否有效")
    print("   - 'NetworkError' - 查看是否有網絡問題")


def main():
    """主函數"""
    print("\n" + "=" * 80)
    print("🤖 X-Piggybacking Telegram 通知診斷工具")
    print("=" * 80)
    print(f"執行時間: {datetime.now(pytz.timezone('Asia/Taipei')).strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Step 1: Check environment variables
    issues, bot_token, chat_id = check_environment_variables()

    # Step 2: Test Telegram connection
    connection_ok = test_telegram_connection(bot_token, chat_id)

    # Step 3: Check Google Sheets data
    check_google_sheets()

    # Step 4: Provide Railway log checking guidance
    check_recent_logs()

    # Summary
    print("\n" + "=" * 80)
    print("📋 診斷總結")
    print("=" * 80)

    if issues:
        print("\n❌ 發現以下問題:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        print("\n💡 解決方案:")
        print("  在 Railway 專案中設置以下環境變數:")
        print("  1. TELEGRAM_BOT_TOKEN=<從 @BotFather 獲得的 token>")
        print("  2. TELEGRAM_CHAT_ID=<你的 Chat ID>")
        print("  3. ENABLE_TELEGRAM_NOTIFICATIONS=true")
        print("\n  設置後需要重新部署服務才會生效。")
    else:
        print("\n✅ 所有環境變數都已正確設置")

    if connection_ok:
        print("\n✅ Telegram 連接測試成功")
        print("   如果您的爬蟲有找到有價值的貼文，應該會收到通知。")
        print("   請檢查:")
        print("   1. 爬蟲是否在預定時間執行 (預設: 每天 08:00 台灣時間)")
        print("   2. LLM 是否判斷任何貼文為有價值")
        print("   3. Railway 日誌中是否有 '[Telegram] Sending daily summary' 訊息")
    else:
        print("\n❌ Telegram 連接測試失敗")
        print("   這可能是訊息沒有發送的原因。")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
