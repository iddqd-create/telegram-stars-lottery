import os
import logging
import requests
from threading import Thread
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
WEBAPP_URL = os.environ.get('WEBAPP_URL', '')

def send_message(chat_id, text, reply_markup=None):
    """Отправить сообщение пользователю"""
    try:
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        
        if reply_markup:
            data['reply_markup'] = reply_markup
        
        response = requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json=data
        )
        
        return response.json()
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return None

def send_winner_notification(user_id, amount, room_id):
    """Отправить уведомление победителю"""
    text = f"""
🎉 <b>Поздравляем! Вы выиграли!</b> 🎉

💰 Приз: <b>{amount} ⭐</b>
🎲 Комната: <code>{room_id[:8]}...</code>

Ваш выигрыш будет зачислен в ближайшее время.

Хотите сыграть еще раз?
"""
    
    keyboard = {
        'inline_keyboard': [[
            {'text': '🎰 Играть снова', 'web_app': {'url': WEBAPP_URL}}
        ]]
    }
    
    send_message(user_id, text, keyboard)

def send_loser_notification(user_id, winner_name, amount, room_id):
    """Отправить уведомление проигравшему"""
    text = f"""
😔 К сожалению, в этот раз не повезло

🏆 Победитель: <b>{winner_name}</b>
💰 Приз: <b>{amount} ⭐</b>
🎲 Комната: <code>{room_id[:8]}...</code>

Не расстраивайтесь! Попробуйте еще раз!
"""
    
    keyboard = {
        'inline_keyboard': [[
            {'text': '🎰 Попробовать снова', 'web_app': {'url': WEBAPP_URL}}
        ]]
    }
    
    send_message(user_id, text, keyboard)

def notify_room_participants(room_data):
    """Уведомить всех участников комнаты о результатах"""
    try:
        winner = room_data['winner']
        winner_user_id = winner['user_id']
        winner_name = winner.get('first_name', winner.get('username', 'Winner'))
        winner_amount = winner['amount']
        room_id = room_data['room_id']
        
        for participant in room_data['participants']:
            user_id = participant['user_id']
            
            if user_id == winner_user_id:
                # Отправляем уведомление победителю
                send_winner_notification(user_id, winner_amount, room_id)
            else:
                # Отправляем уведомление проигравшим
                send_loser_notification(user_id, winner_name, winner_amount, room_id)
        
        logger.info(f"Notifications sent for room {room_id}")
    
    except Exception as e:
        logger.error(f"Error notifying participants: {e}")

def set_bot_commands():
    """Установить команды бота"""
    try:
        commands = [
            {'command': 'start', 'description': 'Запустить лотерею'},
            {'command': 'help', 'description': 'Помощь'},
            {'command': 'stats', 'description': 'Моя статистика'}
        ]
        
        response = requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands',
            json={'commands': commands}
        )
        
        if response.json().get('ok'):
            logger.info("Bot commands set successfully")
        else:
            logger.error(f"Failed to set bot commands: {response.text}")
    
    except Exception as e:
        logger.error(f"Error setting bot commands: {e}")

def handle_start_command(chat_id):
    """Обработать команду /start"""
    text = """
🎰 <b>Добро пожаловать в Stars Lottery!</b> 🎰

Это азартная игра, где <b>6 игроков</b> собираются в комнате, и один счастливчик забирает <b>80% призового фонда</b>!

<b>Как играть:</b>
1️⃣ Выберите размер ставки (50, 100, 250 или 500 ⭐)
2️⃣ Дождитесь заполнения комнаты
3️⃣ Наблюдайте за розыгрышем
4️⃣ Получите приз, если повезет!

<b>Шансы на победу:</b> 1 из 6 (16.67%)
<b>Выигрыш:</b> 80% от общего пула
<b>Комиссия:</b> 20% на развитие проекта

Нажмите кнопку ниже, чтобы начать!
"""
    
    keyboard = {
        'inline_keyboard': [[
            {'text': '🎰 Играть сейчас!', 'web_app': {'url': WEBAPP_URL}}
        ]]
    }
    
    send_message(chat_id, text, keyboard)

def handle_help_command(chat_id):
    """Обработать команду /help"""
    text = """
❓ <b>Помощь - Stars Lottery</b>

<b>Доступные команды:</b>
/start - Запустить лотерею
/help - Показать эту справку
/stats - Посмотреть свою статистику

<b>Правила игры:</b>
• В каждой комнате 6 участников
• Все платят одинаковую ставку
• Один случайный участник выигрывает 80% пула
• 20% идет на развитие проекта

<b>Размеры ставок:</b>
• 50 ⭐ - выигрыш до 240 ⭐
• 100 ⭐ - выигрыш до 480 ⭐
• 250 ⭐ - выигрыш до 1,200 ⭐
• 500 ⭐ - выигрыш до 2,400 ⭐

<b>Поддержка:</b>
По всем вопросам: @klimaz
"""
    
    send_message(chat_id, text)

def handle_stats_command(chat_id):
    """Обработать команду /stats"""
    # TODO: Получить статистику из БД
    text = """
📊 <b>Ваша статистика</b>

🎮 Игр сыграно: 0
🏆 Побед: 0
📈 Процент побед: 0%
💰 Всего выиграно: 0 ⭐
💸 Всего потрачено: 0 ⭐

Откройте приложение для подробной статистики!
"""
    
    keyboard = {
        'inline_keyboard': [[
            {'text': '📊 Открыть статистику', 'web_app': {'url': WEBAPP_URL}}
        ]]
    }
    
    send_message(chat_id, text, keyboard)

def process_updates():
    """Обработать обновления от Telegram (polling mode для разработки)"""
    offset = 0
    
    while True:
        try:
            response = requests.get(
                f'https://api.telegram.org/bot{BOT_TOKEN}/getUpdates',
                params={'offset': offset, 'timeout': 30}
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get updates: {response.text}")
                time.sleep(5)
                continue
            
            data = response.json()
            
            if not data.get('ok'):
                logger.error(f"API error: {data}")
                time.sleep(5)
                continue
            
            updates = data.get('result', [])
            
            for update in updates:
                offset = update['update_id'] + 1
                
                if 'message' in update:
                    message = update['message']
                    chat_id = message['chat']['id']
                    text = message.get('text', '')
                    
                    if text.startswith('/start'):
                        handle_start_command(chat_id)
                    elif text.startswith('/help'):
                        handle_help_command(chat_id)
                    elif text.startswith('/stats'):
                        handle_stats_command(chat_id)
        
        except Exception as e:
            logger.error(f"Error processing updates: {e}")
            time.sleep(5)

def start_bot_polling():
    """Запустить бота в режиме polling (для разработки)"""
    logger.info("Starting bot in polling mode...")
    set_bot_commands()
    
    thread = Thread(target=process_updates, daemon=True)
    thread.start()
    
    logger.info("Bot polling started")

if __name__ == '__main__':
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
    else:
        start_bot_polling()
        
        # Keep the script running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Bot stopped")
