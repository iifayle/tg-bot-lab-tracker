import json
import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

import os
BOT_TOKEN = os.environ.get("BOT_TOKEN")

DATA_FILE = "subjects_data.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# РАБОТА С ФАЙЛОМ JSON 

import urllib.request

UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

def _redis_command(*args):
    if not UPSTASH_URL or not UPSTASH_TOKEN:
        return None
    req = urllib.request.Request(
        UPSTASH_URL,
        data=json.dumps([str(a) for a in args]).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {UPSTASH_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return (json.loads(r.read() or b"{}") or {}).get("result")

def load_data():
    try:
        raw = _redis_command("GET", "bot:lab_tracker_data")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}

def save_data(data):
    try:
        _redis_command("SET", "bot:lab_tracker_data", json.dumps(data, ensure_ascii=False))
    except Exception as e:
        print("Ошибка сохранения в Redis:", e)
    """Сохраняет данные в файл"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_data(user_id):
    """Получает данные конкретного пользователя"""
    data = load_data()
    user_id_str = str(user_id)
    if user_id_str not in data:
        data[user_id_str] = {"subjects": {}, "last_update": None}
        save_data(data)
    return data, data[user_id_str]

def save_user_data(user_id, user_data):
    """Сохраняет данные конкретного пользователя"""
    data = load_data()
    data[str(user_id)] = user_data
    save_data(data)


def calculate_statistics(subjects):
    """Рассчитывает статистику по всем предметам"""
    total_labs = 0
    total_done = 0
    
    for name, info in subjects.items():
        total_labs += info["total"]
        total_done += info["done"]
    
    total_remaining = total_labs - total_done
    
    return {
        "total_labs": total_labs,
        "total_done": total_done,
        "total_remaining": total_remaining,
        "subjects_count": len(subjects)
    }

def make_progress_bar(done, total, length=10):
    """Создаёт прогресс-бар"""
    if total == 0:
        return "-" * length
    filled = int((done / total) * length)
    empty = length - filled
    return "+" * filled + "-" * empty

# КЛАВИАТУРЫ 

def get_main_keyboard():
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton("Добавить предмет", callback_data="add_subject")],
        [InlineKeyboardButton("Отметить сданные лабы", callback_data="mark_done")],
        [InlineKeyboardButton("Показать статистику", callback_data="show_stats")],
        [InlineKeyboardButton("Список предметов", callback_data="list_subjects")],
        [InlineKeyboardButton("Удалить предмет", callback_data="delete_subject")],
        [InlineKeyboardButton("Помощь", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

#  ОБРАБОТЧИК КОМАНДЫ /start

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    _, user_data = get_user_data(user_id)
    
    context.user_data.clear()
    
    if not user_data["subjects"]:
        await update.message.reply_text(
            "🎓 *Трекер лабораторных работ*\n\n"
            "Я помогу тебе отслеживать прогресс по сдаче лабораторных работ!\n\n"
            "*Что я умею:*\n"
            "• Добавлять предметы и количество лабораторных\n"
            "• Отмечать СКОЛЬКО лаб сдано \n"
            "• Показывать статистику (сколько осталось)\n"
            "• Хранить данные в файле\n\n"
            "*Начни с добавления первого предмета!*",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "*Трекер лабораторных работ*\n\n"
            "Ты уже в системе! Выбери действие:",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )

# ОБРАБОТЧИК КНОПОК 

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на инлайн-кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data, user_data = get_user_data(user_id)
    action = query.data
    
    #  Помощь
    if action == "help":
        await query.edit_message_text(
            "*Помощь*\n\n"
            "*Добавить предмет* - добавить новый предмет и указать количество лаб\n"
            "*Отметить сданные лабы* - выбрать предмет и ВВЕСТИ ЧИСЛО (сколько сдал)\n"
            "*Статистика* - показать общий прогресс\n"
            "*Список предметов* - посмотреть все предметы\n"
            "*Удалить предмет* - удалить предмет\n\n"
            "*Пример:* если у тебя 14 лаб по ДПИ, и ты сдал 12 — введи 12, и бот всё посчитает!",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    if action == "show_stats":
        if not user_data["subjects"]:
            await query.edit_message_text(
                "*Нет данных!*\n\nДобавь первый предмет через главное меню.",
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
            return
        
        stats = calculate_statistics(user_data["subjects"])
        
        message = "*Твоя статистика*\n\n"
        message += f"*Всего предметов:* {stats['subjects_count']}\n"
        message += f"*Всего лабораторных:* {stats['total_labs']}\n"
        message += f"*Сдано:* {stats['total_done']}\n"
        message += f"*Осталось сдать:* {stats['total_remaining']}\n\n"
        
        if stats['total_labs'] > 0:
            progress = (stats['total_done'] / stats['total_labs']) * 100
            message += f"*Общий прогресс:* {progress:.1f}%\n\n"
        
        message += "*По предметам:*\n"
        for name, info in user_data["subjects"].items():
            remaining = info["total"] - info["done"]
            progress_bar = make_progress_bar(info["done"], info["total"])
            message += f"\n*{name}*\n"
            message += f"   {progress_bar} {info['done']}/{info['total']}\n"
            message += f"   Осталось: {remaining}\n"
        
        await query.edit_message_text(
            message,
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    if action == "list_subjects":
        if not user_data["subjects"]:
            await query.edit_message_text(
                "📭 *Нет предметов!*\n\nДобавь первый предмет.",
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
            return
        
        message = "*Список предметов*\n\n"
        for name, info in user_data["subjects"].items():
            remaining = info["total"] - info["done"]
            message += f"📖 *{name}*\n"
            message += f"   Лабораторных: {info['total']}\n"
            message += f"   Сдано: {info['done']}\n"
            message += f"   Осталось: {remaining}\n\n"
        
        await query.edit_message_text(
            message,
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
        return
    
    if action == "add_subject":
        context.user_data["waiting_for"] = "subject_name"
        await query.edit_message_text(
            "*Добавление предмета*\n\n"
            "Введите *название предмета*:\n"
            "Например: `ВЯП`, `ООП`, `БД`, `ДПИ`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Отмена", callback_data="back_to_main")]]),
            parse_mode="Markdown"
        )
        return
    
    if action == "mark_done":
        if not user_data["subjects"]:
            await query.edit_message_text(
                "*Нет предметов!*\n\nСначала добавь предмет.",
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
            return
        
        keyboard = []
        for name in user_data["subjects"].keys():
            info = user_data["subjects"][name]
            keyboard.append([InlineKeyboardButton(
                f"{name} (сдано: {info['done']}/{info['total']})", 
                callback_data=f"select_{name}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
        
        await query.edit_message_text(
            "*Отметить сданные лабораторные*\n\n"
            "Выбери предмет, а затем *введи число* — сколько лаб ты сдал(а):\n\n"
            "*Пример:* если по ДПИ сдала 12 из 14, выбери ДПИ и введи `12`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    if action.startswith("select_"):
        subject_name = action[7:]
        context.user_data["marking_subject"] = subject_name
        context.user_data["waiting_for"] = "mark_count"
        
        current_total = user_data["subjects"][subject_name]["total"]
        current_done = user_data["subjects"][subject_name]["done"]
        
        await query.edit_message_text(
            f"*{subject_name}*\n\n"
            f"Всего лаб: *{current_total}*\n"
            f"Уже сдано: *{current_done}*\n"
            f"Осталось: *{current_total - current_done}*\n\n"
            f"*Введите общее количество сданных лаб* (числом):\n\n"
            f"Например, если сдала 12, введи `12`",
            parse_mode="Markdown"
        )
        return
    
    # === Удалить предмет ===
    if action == "delete_subject":
        if not user_data["subjects"]:
            await query.edit_message_text(
                "*Нет предметов!*",
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
            return
        
        keyboard = []
        for name in user_data["subjects"].keys():
            keyboard.append([InlineKeyboardButton(f"{name}", callback_data=f"delete_{name}")])
        keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_main")])
        
        await query.edit_message_text(
            "*Удаление предмета*\n\nВсе данные по предмету будут потеряны!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    # Обработка удаления
    if action.startswith("delete_"):
        subject_name = action[7:]
        if subject_name in user_data["subjects"]:
            del user_data["subjects"][subject_name]
            user_data["last_update"] = datetime.now().isoformat()
            save_user_data(user_id, user_data)
            await query.edit_message_text(
                f"*'{subject_name}' удалён!*",
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
        return
    
    # === Назад в главное меню ===
    if action == "back_to_main":
        await query.edit_message_text(
            "🎓 *Главное меню*\n\nВыбери действие:",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
        return

# ОБРАБОТЧИК ТЕКСТОВЫХ ВВОДОВ 

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода: название предмета, количество лаб, отметка сданных"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    waiting_for = context.user_data.get("waiting_for")
    
    # === Добавление предмета: ввод названия ===
    if waiting_for == "subject_name":
        context.user_data["temp_subject_name"] = text
        context.user_data["waiting_for"] = "subject_total"
        await update.message.reply_text(
            f"*Предмет: {text}*\n\nВведите *общее количество лабораторных* (числом):",
            parse_mode="Markdown"
        )
        return
    
    # === Добавление предмета: ввод количества лаб ===
    if waiting_for == "subject_total":
        try:
            total = int(text)
            if total <= 0:
                await update.message.reply_text("Введите положительное число!")
                return
            
            subject_name = context.user_data.get("temp_subject_name")
            data, user_data = get_user_data(user_id)
            
            user_data["subjects"][subject_name] = {"total": total, "done": 0}
            user_data["last_update"] = datetime.now().isoformat()
            save_user_data(user_id, user_data)
            
            context.user_data.pop("temp_subject_name", None)
            context.user_data.pop("waiting_for", None)
            
            await update.message.reply_text(
                f"*'{subject_name}' добавлен!*\n\n"
                f"Всего лабораторных: *{total}*\n"
                f"Сдано: *0*\n"
                f"Осталось: *{total}*\n\n"
                f"Теперь можно отмечать сданные лабы! ",
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text(" Ошибка! Введите ЧИСЛО (количество лабораторных):")
        return
    
    # === Отметка сданных лаб: ввод количества ===
    if waiting_for == "mark_count":
        try:
            done_count = int(text)
            subject_name = context.user_data.get("marking_subject")
            
            if not subject_name:
                await update.message.reply_text(" Ошибка! Попробуй ещё раз через меню.")
                context.user_data.pop("waiting_for", None)
                return
            
            data, user_data = get_user_data(user_id)
            
            if subject_name not in user_data["subjects"]:
                await update.message.reply_text(" Предмет не найден!")
                context.user_data.pop("waiting_for", None)
                return
            
            total = user_data["subjects"][subject_name]["total"]
            
            # Проверка на корректность ввода
            if done_count < 0:
                await update.message.reply_text(" Количество не может быть отрицательным!")
                return
            if done_count > total:
                await update.message.reply_text(
                    f"Нельзя сдать больше, чем есть!\n"
                    f"Всего лаб: *{total}*\n"
                    f"Пожалуйста, введите число от 0 до {total}:",
                    parse_mode="Markdown"
                )
                return
            
            # Обновляем количество сданных
            old_done = user_data["subjects"][subject_name]["done"]
            user_data["subjects"][subject_name]["done"] = done_count
            user_data["last_update"] = datetime.now().isoformat()
            save_user_data(user_id, user_data)
            
            remaining = total - done_count
            
            progress_bar = make_progress_bar(done_count, total)
            
            await update.message.reply_text(
                f"*Обновлено!*\n\n"
                f"*{subject_name}*\n"
                f" {progress_bar} {done_count}/{total}\n\n"
                f"Было сдано: *{old_done}*\n"
                f"Стало сдано: *{done_count}*\n"
                f"Осталось сдать: *{remaining}*\n\n"
                f"Так держать! ",
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
            
            # Очищаем состояние
            context.user_data.pop("marking_subject", None)
            context.user_data.pop("waiting_for", None)
            
        except ValueError:
            await update.message.reply_text("Ошибка! Введите ЧИСЛО (сколько лаб сдано):")
        return

#ОБРАБОТЧИК ДЛЯ НЕКОРРЕКТНЫХ ДАННЫХ 

async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Реакция на неизвестные сообщения"""
    await update.message.reply_text(
        "*Я не понимаю*\n\nИспользуй кнопки меню или напиши /start",
        parse_mode="Markdown"
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    app.add_handler(MessageHandler(filters.ALL, handle_unknown))
    
    print("Бот-трекер лабораторных работ запущен!")
    print("Данные сохраняются в файл:", DATA_FILE)
    print("Теперь можно отмечать СКОЛЬКО лаб сдано одним числом!")
    app.run_polling()

if __name__ == "__main__":
    main()