import asyncio
import logging
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from supabase import create_client

# ===== НАСТРОЙКИ (ЗАМЕНИТЕ НА СВОИ) =====
TELEGRAM_TOKEN = "8553072359:AAH-OjYeKSuOx4rPefhVWvAsYVYrYJFGi1o"
SUPABASE_URL = "https://jkmqigxiynvdgzlcmhil.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImprbXFpZ3hpeW52ZGd6bGNtaGlsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Mzc2NDA4MywiZXhwIjoyMDg5MzQwMDgzfQ.o-Wkb2b_vS0-TTl6iFREE_FpKeBocpZPKlvn6bTJ9qU"
# ========================================

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

logging.basicConfig(level=logging.INFO)

class AddClothesStates(StatesGroup):
    waiting_photo = State()
    waiting_type = State()
    waiting_description = State()

# Клавиатуры
def get_main_keyboard():
    kb = [
        [KeyboardButton(text="👗 Мой гардероб"), KeyboardButton(text="🤔 Что надеть?")],
        [KeyboardButton(text="➕ Добавить вещь"), KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# Команда /start
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("👋 Привет! Я бот для управления твоим гардеробом.\n\nДобавляй вещи, смотри гардероб, получай идеи образов.", reply_markup=get_main_keyboard())

# Команда /help
@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer("📋 Команды:\n/add_clothes — добавить вещь\n/my_wardrobe — показать гардероб\n/delete_clothes — удалить вещь\n/look — что надеть сегодня\n/start — главное меню")

# Кнопка "➕ Добавить вещь"
@dp.message(F.text == "➕ Добавить вещь")
async def add_clothes_button(message: Message, state: FSMContext):
    await message.answer("📸 Отправь фотографию вещи.")
    await state.set_state(AddClothesStates.waiting_photo)

# Команда /add_clothes
@dp.message(Command("add_clothes"))
async def add_clothes_cmd(message: Message, state: FSMContext):
    await message.answer("📸 Отправь фотографию вещи.")
    await state.set_state(AddClothesStates.waiting_photo)

@dp.message(AddClothesStates.waiting_photo, F.photo)
async def got_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=file_id)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Футболка"), KeyboardButton(text="Джинсы")],
            [KeyboardButton(text="Пальто"), KeyboardButton(text="Обувь")],
            [KeyboardButton(text="Пропустить")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выбери тип одежды или 'Пропустить':", reply_markup=kb)
    await state.set_state(AddClothesStates.waiting_type)

@dp.message(AddClothesStates.waiting_type, F.text)
async def got_type(message: Message, state: FSMContext):
    text = message.text
    clothing_type = None if text == "Пропустить" else text
    await state.update_data(clothing_type=clothing_type)
    await message.answer("Теперь напиши описание (цвет, материал и т.д.) или 'Пропустить':",
                         reply_markup=ReplyKeyboardMarkup.from_button(KeyboardButton(text="Пропустить"), resize_keyboard=True))
    await state.set_state(AddClothesStates.waiting_description)

@dp.message(AddClothesStates.waiting_description, F.text)
async def got_description(message: Message, state: FSMContext):
    description = None if message.text == "Пропустить" else message.text
    data = await state.get_data()
    photo_file_id = data['photo_file_id']
    clothing_type = data['clothing_type']
    user_id = str(message.from_user.id)

    # Получаем ссылку на фото
    file_info = await bot.get_file(photo_file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"

    # Загружаем фото в Supabase Storage (бакет "Гардероб" или "wardrobe")
    bucket_name = "Гардероб"  # Укажите точное имя вашего бакета
    file_name = f"{user_id}_{int(datetime.now().timestamp())}.jpg"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                image_bytes = await resp.read()
        supabase.storage.from_(bucket_name).upload(file_name, image_bytes, {"content-type": "image/jpeg"})
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
    except Exception as e:
        logging.error(f"Ошибка загрузки фото: {e}")
        await message.answer("❌ Не удалось сохранить фото. Проверьте настройки бакета.")
        await state.clear()
        return

    # Сохраняем в таблицу wardrobe
    try:
        supabase.table('wardrobe').insert({
            'user_id': user_id,
            'image_url': public_url,
            'clothing_type': clothing_type,
            'description': description
        }).execute()
        await message.answer("✅ Вещь добавлена в гардероб!", reply_markup=get_main_keyboard())
    except Exception as e:
        logging.error(f"Ошибка Supabase: {e}")
        await message.answer("❌ Ошибка при сохранении в базу данных.")
    finally:
        await state.clear()

# Кнопка "👗 Мой гардероб"
@dp.message(F.text == "👗 Мой гардероб")
async def my_wardrobe_button(message: Message):
    await show_wardrobe(message)

# Команда /my_wardrobe
@dp.message(Command("my_wardrobe"))
async def my_wardrobe_cmd(message: Message):
    await show_wardrobe(message)

async def show_wardrobe(message: Message):
    user_id = str(message.from_user.id)
    resp = supabase.table('wardrobe').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
    items = resp.data
    if not items:
        await message.answer("📭 Твой гардероб пуст. Добавь вещи командой /add_clothes")
        return
    for item in items:
        buttons = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_{item['id']}")]
        ])
        caption = f"<b>{item['clothing_type'] or 'Вещь'}</b>\n{item['description'] or ''}"
        try:
            await bot.send_photo(chat_id=message.chat.id, photo=item['image_url'],
                                 caption=caption, reply_markup=buttons, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Ошибка отправки фото: {e}")
            await message.answer(f"⚠️ Не удалось показать одну из вещей (ID {item['id']}). Возможно, фото удалено.")

@dp.callback_query(lambda c: c.data and c.data.startswith("del_"))
async def delete_item(callback: CallbackQuery):
    item_id = int(callback.data.split("_")[1])
    user_id = str(callback.from_user.id)
    # Удаляем запись
    supabase.table('wardrobe').delete().eq('id', item_id).eq('user_id', user_id).execute()
    # Также можно удалить файл из Storage, но для простоты пропустим
    await callback.answer("Вещь удалена из гардероба")
    await callback.message.delete()

# Кнопка "🤔 Что надеть?"
@dp.message(F.text == "🤔 Что надеть?")
async def look_button(message: Message):
    await look(message)

# Команда /look
@dp.message(Command("look"))
async def look_cmd(message: Message):
    await look(message)

async def look(message: Message):
    user_id = str(message.from_user.id)
    resp = supabase.table('wardrobe').select('*').eq('user_id', user_id).execute()
    items = resp.data
    if len(items) < 2:
        await message.answer("Добавь хотя бы 2 вещи, чтобы я мог составить образ.")
        return
    import random
    selected = random.sample(items, min(3, len(items)))
    outfits = [f"{item['clothing_type'] or 'Вещь'}: {item['description'] or 'без описания'}" for item in selected]
    answer = "✨ <b>Твой образ на сегодня:</b>\n\n" + "\n".join(outfits)
    await message.answer(answer, parse_mode="HTML")

# Команда /delete_clothes
@dp.message(Command("delete_clothes"))
async def delete_cmd(message: Message):
    await message.answer("Используй кнопку «Удалить» под каждой вещью в разделе «Мой гардероб».")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
