import telebot
import pandas as pd
import numpy as np
import random
from telebot import types
import os
from collections import defaultdict

# Bot token - replace with your actual bot token
BOT_TOKEN = "your_token"

bot = telebot.TeleBot(BOT_TOKEN)

# Global variables to store user states
user_states = defaultdict(dict)
user_dislikes = defaultdict(int)
user_last_message_id = defaultdict(int)  # Track last message IDs

# Categories array
CATEGORIES = ['art', 'kids', 'history', 'biography', 'education', 'programming', 'romance', 'psychology', 'science', 'fantasy']

# Russian category names
CATEGORY_NAMES_RU = {
    'art': 'Искусство',
    'kids': 'Детские',
    'history': 'История',
    'biography': 'Биография',
    'education': 'Образование',
    'programming': 'Программирование',
    'romance': 'Романтика',
    'psychology': 'Психология',
    'science': 'Наука',
    'fantasy': 'Фэнтези'
}

# Prices are already in tenge

# Load the embedded flip books data
def load_flip_books_data():
    """
    Load your flip_books_data_embedded here
    """
    data = pd.read_csv(r"C:\Users\User\Desktop\DATA SCIENCE\Github\flip_book\data\flip_books_data_embeded_clustered.csv.gz")
    return pd.DataFrame(data)

# Load data
books_df = load_flip_books_data()

def format_price_with_discount(price_kzt, discount):
    """Format price with discount in tenge"""
    discounted_price_kzt = price_kzt * (1 - discount / 100)
    return f"₸{discounted_price_kzt:,.0f} (скидка {discount}% от ₸{price_kzt:,.0f})"

def create_category_keyboard():
    """Create inline keyboard for category selection"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    
    for category in CATEGORIES:
        button = types.InlineKeyboardButton(
            text=CATEGORY_NAMES_RU[category],
            callback_data=f"category_{category}"
        )
        buttons.append(button)
    
    # Add buttons in rows of 2
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            keyboard.row(buttons[i], buttons[i + 1])
        else:
            keyboard.row(buttons[i])
    
    return keyboard

def create_book_action_keyboard():
    """Create keyboard for book actions (like/dislike)"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    like_btn = types.InlineKeyboardButton("👍 Нравится", callback_data="like")
    dislike_btn = types.InlineKeyboardButton("👎 Не нравится", callback_data="dislike")
    new_category_btn = types.InlineKeyboardButton("📚 Новая категория", callback_data="new_category")
    
    keyboard.row(like_btn, dislike_btn)
    keyboard.row(new_category_btn)
    
    return keyboard

def get_random_book_from_category(category):
    """Get a random book from specified category"""
    category_books = books_df[books_df['category'] == category]
    if len(category_books) == 0:
        return None
    return category_books.sample(n=1).iloc[0]

def get_similar_books(category, cluster_id):
    """Get books from same category and cluster"""
    similar_books = books_df[
        (books_df['category'] == category) & 
        (books_df['kmeans21_cluster'] == cluster_id)
    ]
    if len(similar_books) == 0:
        return None
    return similar_books.sample(n=1).iloc[0]

def send_book_info(chat_id, book):
    """Send book information to user"""
    title = book['title']
    price = book['price_original']
    discount = int(book['discount'])
    description = book['description']
    image_path = book['windows_image_path']
    
    formatted_price = format_price_with_discount(price, discount)
    
    message = f"📖 *{title}*\n\n"
    message += f"💰 Цена: {formatted_price}\n\n"
    message += f"📝 Описание: {description}\n\n"
    message += f"📂 Категория: {CATEGORY_NAMES_RU[book['category']]}"
    
    keyboard = create_book_action_keyboard()
    
    # Try to send image if path exists
    try:
        if os.path.exists(image_path):
            with open(image_path, 'rb') as photo:
                sent_message = bot.send_photo(
                    chat_id,
                    photo,
                    caption=message,
                    parse_mode='Markdown',
                    reply_markup=keyboard
                )
                # Store the message ID for future edits
                user_last_message_id[chat_id] = sent_message.message_id
        else:
            # Send text message if image doesn't exist
            sent_message = bot.send_message(
                chat_id,
                message,
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            user_last_message_id[chat_id] = sent_message.message_id
    except Exception as e:
        # Fallback to text message
        sent_message = bot.send_message(
            chat_id,
            message,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        user_last_message_id[chat_id] = sent_message.message_id

def send_status_message(chat_id, text):
    """Send a status message and store its ID for editing"""
    try:
        sent_message = bot.send_message(chat_id, text, parse_mode='Markdown')
        user_last_message_id[chat_id] = sent_message.message_id
        return sent_message
    except Exception:
        return None

@bot.message_handler(commands=['start'])
def start_command(message):
    """Handle /start command"""
    welcome_text = """
🤖 Добро пожаловать в flip_book_bot бот! 📚

Я помогу вам найти удивительные книги на основе ваших предпочтений.

Выберите категорию для начала:
    """
    
    keyboard = create_category_keyboard()
    sent_message = bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=keyboard
    )
    user_last_message_id[message.chat.id] = sent_message.message_id

@bot.callback_query_handler(func=lambda call: call.data.startswith('category_'))
def handle_category_selection(call):
    """Handle category selection"""
    category = call.data.replace('category_', '')
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    # Reset user state
    user_states[user_id] = {
        'category': category,
        'mode': 'random',
        'current_cluster': None
    }
    user_dislikes[user_id] = 0
    
    # Get random book from category
    book = get_random_book_from_category(category)
    
    if book is not None:
        user_states[user_id]['current_book'] = book
        
        # Try to edit the message, if it fails, send a new one
        try:
            bot.edit_message_text(
                f"📚 Выбрана категория: *{CATEGORY_NAMES_RU[category]}*\n\nВот рекомендация книги:",
                chat_id,
                call.message.message_id,
                parse_mode='Markdown'
            )
        except Exception:
            # If editing fails, send a new message
            send_status_message(chat_id, f"📚 Выбрана категория: *{CATEGORY_NAMES_RU[category]}*\n\nВот рекомендация книги:")
        
        send_book_info(chat_id, book)
    else:
        try:
            bot.edit_message_text(
                f"Извините, книги в категории {CATEGORY_NAMES_RU[category]} не найдены",
                chat_id,
                call.message.message_id
            )
        except Exception:
            send_status_message(chat_id, f"Извините, книги в категории {CATEGORY_NAMES_RU[category]} не найдены")

@bot.callback_query_handler(func=lambda call: call.data == 'like')
def handle_like(call):
    """Handle like button press"""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    if user_id not in user_states:
        bot.answer_callback_query(call.id, "Пожалуйста, начните с выбора категории!")
        return
    
    # Reset dislike counter
    user_dislikes[user_id] = 0
    
    current_book = user_states[user_id].get('current_book')
    if current_book is None:
        bot.answer_callback_query(call.id, "Текущая книга не найдена!")
        return
    
    # Switch to cluster mode
    user_states[user_id]['mode'] = 'cluster'
    user_states[user_id]['current_cluster'] = current_book['kmeans21_cluster']
    
    category = user_states[user_id]['category']
    cluster_id = current_book['kmeans21_cluster']
    
    # Get similar book
    similar_book = get_similar_books(category, cluster_id)
    
    if similar_book is not None:
        user_states[user_id]['current_book'] = similar_book
        send_status_message(chat_id, "👍 Отличный выбор! Вот похожая книга, которая может вам понравиться:")
        send_book_info(chat_id, similar_book)
    else:
        # Fallback to random if no similar books
        random_book = get_random_book_from_category(category)
        if random_book is not None:
            user_states[user_id]['current_book'] = random_book
            user_states[user_id]['mode'] = 'random'
            send_status_message(chat_id, "👍 Понравилось! Вот еще одна книга из вашей категории:")
            send_book_info(chat_id, random_book)
    
    bot.answer_callback_query(call.id, "👍 Понравилось!")

@bot.callback_query_handler(func=lambda call: call.data == 'dislike')
def handle_dislike(call):
    """Handle dislike button press"""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    if user_id not in user_states:
        bot.answer_callback_query(call.id, "Пожалуйста, начните с выбора категории!")
        return
    
    # Increment dislike counter
    user_dislikes[user_id] += 1
    
    category = user_states[user_id]['category']
    current_mode = user_states[user_id]['mode']
    
    # Check if user disliked 5 times in a row
    if user_dislikes[user_id] >= 5:
        # Reset to random mode
        user_states[user_id]['mode'] = 'random'
        user_states[user_id]['current_cluster'] = None
        user_dislikes[user_id] = 0
        
        random_book = get_random_book_from_category(category)
        if random_book is not None:
            user_states[user_id]['current_book'] = random_book
            send_status_message(chat_id, "🔄 Давайте попробуем что-то совершенно другое! Вот случайная книга:")
            send_book_info(chat_id, random_book)
        
        bot.answer_callback_query(call.id, "🔄 Переключаемся на случайные рекомендации!")
        return
    
    # Get next book based on current mode
    if current_mode == 'cluster' and user_states[user_id].get('current_cluster') is not None:
        # Get another book from same cluster
        cluster_id = user_states[user_id]['current_cluster']
        next_book = get_similar_books(category, cluster_id)
    else:
        # Get random book
        next_book = get_random_book_from_category(category)
    
    if next_book is not None:
        user_states[user_id]['current_book'] = next_book
        dislike_count = user_dislikes[user_id]
        remaining = 5 - dislike_count
        
        send_status_message(chat_id, f"👎 Не проблема! Вот еще одна книга (еще {remaining} дизлайков до случайного режима):")
        send_book_info(chat_id, next_book)
    
    bot.answer_callback_query(call.id, "👎 Не понравилось!")

@bot.callback_query_handler(func=lambda call: call.data == 'new_category')
def handle_new_category(call):
    """Handle new category button press"""
    chat_id = call.message.chat.id
    keyboard = create_category_keyboard()
    
    try:
        bot.edit_message_text(
            "📚 Выберите новую категорию:",
            chat_id,
            call.message.message_id,
            reply_markup=keyboard
        )
    except Exception:
        # If editing fails, send a new message
        sent_message = bot.send_message(
            chat_id,
            "📚 Выберите новую категорию:",
            reply_markup=keyboard
        )
        user_last_message_id[chat_id] = sent_message.message_id
    
    bot.answer_callback_query(call.id, "Выбор новой категории!")

# Error handler
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """Handle all other messages"""
    bot.reply_to(message, "Используйте /start для начала работы с ботом!")

if __name__ == "__main__":
    print("Бот запущен...")
    bot.polling(none_stop=True)
