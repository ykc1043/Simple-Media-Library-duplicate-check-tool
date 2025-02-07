#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import telebot
from config import bot_token, admin_list
import multiprocessing
import time
import threading
from app import app  # 导入 Flask 应用

# 初始化 Telegram Bot
bot = telebot.TeleBot(bot_token)

# 全局变量管理 Web 进程和聊天 ID
web_process = None
web_started_chat_id = None
web_check_interval = 5  # 检查状态间隔（秒）
lock = threading.Lock()  # 线程锁防止竞争条件

def is_web_running():
    """检查 Web 进程是否在运行"""
    global web_process
    return web_process is not None and web_process.is_alive()

def check_web_status():
    """后台线程定期检查 Web 状态"""
    global web_process, web_started_chat_id
    while True:
        with lock:
            if web_started_chat_id is not None and not is_web_running():
                print("【调试】检测到 Web 服务已关闭")
                try:
                    bot.send_message(web_started_chat_id, "检测到 Web 服务已关闭")
                except Exception as e:
                    print(f"【调试】发送消息失败: {e}")
                web_started_chat_id = None
                web_process = None
        time.sleep(web_check_interval)

# 启动后台检查线程
threading.Thread(target=check_web_status, daemon=True).start()

@bot.message_handler(commands=['manage'])
def handle_manage(message):
    """处理 /manage 命令启动 Web 服务"""
    global web_process, web_started_chat_id
    print(f"【调试】收到 /manage 命令，来自用户 {message.from_user.id}")
    if message.from_user.id not in admin_list:
        bot.reply_to(message, "⚠️ 权限不足")
        return

    with lock:
        if is_web_running():
            bot.reply_to(message, "🔄 Web 服务正在运行中，请先关闭后再启动。")
            return

        try:
            print("【调试】启动 Web 进程")
            web_process = multiprocessing.Process(
                target=app.run,
                kwargs={'host': "::", 'port': 5000, 'use_reloader': False}  # 改为IPv4地址监听
            )
            web_process.start()
            web_started_chat_id = message.chat.id
            print("【调试】Web 进程启动成功")

            # 发送带按钮的控制面板
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton(
                "🔴 关闭 Web 服务",
                callback_data='shutdown_web'
            ))
            bot.send_message(
                message.chat.id,
                "✅ Web 服务已启动\n\n"
                "访问地址: http://你的服务器IP:5000\n"
                "点击下方按钮关闭服务:",
                reply_markup=markup
            )
        except Exception as e:
            print(f"【调试】启动 Web 进程失败: {e}")
            bot.reply_to(message, f"❌ 启动失败: {str(e)}")

# 捕获所有回调更新（方便调试）
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    print(f"【调试】收到回调: {call.data}")
    if call.data == 'shutdown_web':
        handle_shutdown(call)
    else:
        bot.answer_callback_query(call.id, "未知操作")

def handle_shutdown(call):
    """处理关闭 Web 服务的回调"""
    global web_process, web_started_chat_id
    with lock:
        if not is_web_running():
            print("【调试】收到关闭请求，但 Web 服务未运行")
            bot.answer_callback_query(call.id, "⚠️ Web 服务未运行")
            return

        print("【调试】关闭服务按钮按下")
        try:
            # 尝试终止进程
            web_process.terminate()
            bot.answer_callback_query(call.id, "⌛ 正在关闭...")

            # 等待最多5秒
            timeout = 5
            start_time = time.time()
            while time.time() - start_time < timeout:
                if not web_process.is_alive():
                    break
                time.sleep(0.5)
            else:
                bot.send_message(call.message.chat.id, "⏳ 关闭超时，强制终止中...")
                web_process.kill()

            web_process.join()
            web_process = None
            web_started_chat_id = None
            bot.edit_message_text(
                "✅ Web 服务已关闭",
                call.message.chat.id,
                call.message.message_id
            )
            print("【调试】Web 服务关闭成功")
        except Exception as e:
            print(f"【调试】关闭 Web 服务时发生异常: {e}")
            bot.send_message(call.message.chat.id, f"❌ 关闭服务失败: {e}")

if __name__ == "__main__":
    print("Telegram Bot 已启动...")
    try:
        # 确保接收包括回调查询在内的所有更新
        bot.infinity_polling(allowed_updates=["message", "callback_query"])
    except Exception as e:
        print(f"【调试】Bot polling 发生异常: {e}")

