import os
import hmac
import hashlib
import json
import time
import sqlite3
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from marshmallow import Schema, fields, validate, ValidationError
import requests
from threading import Lock
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Rate Limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
ADMIN_USERNAME = 'klimaz'
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '')

# Константы
ENTRY_FEES = [50, 100, 250, 500]  # Стоимость входа в Stars
MAX_ROOM_SIZE = 6
WINNER_PERCENTAGE = 0.80  # 80% победителю
ADMIN_PERCENTAGE = 0.20   # 20% админу
LOTTERY_DURATION = 10     # Секунд анимации розыгрыша

# Глобальное состояние комнат (в продакшене использовать Redis)
rooms: Dict[str, Dict] = {}
rooms_lock = Lock()

# База данных
DB_PATH = 'lottery.db'

# Validation Schemas
class CreateInvoiceSchema(Schema):
    initData = fields.Str(required=True)
    entryFee = fields.Int(required=True, validate=validate.OneOf(ENTRY_FEES))

class UserInfoSchema(Schema):
    initData = fields.Str(required=True)

def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Таблица платежей
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        telegram_payment_charge_id TEXT UNIQUE,
        status TEXT,
        room_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )''')
    
    # Таблица комнат
    c.execute('''CREATE TABLE IF NOT EXISTS rooms (
        room_id TEXT PRIMARY KEY,
        entry_fee INTEGER,
        status TEXT,
        winner_user_id INTEGER,
        total_pool INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY (winner_user_id) REFERENCES users(user_id)
    )''')
    
    # Таблица участников комнат
    c.execute('''CREATE TABLE IF NOT EXISTS room_participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id TEXT,
        user_id INTEGER,
        payment_id INTEGER,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (room_id) REFERENCES rooms(room_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (payment_id) REFERENCES payments(id)
    )''')
    
    # Таблица транзакций (для аудита)
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id TEXT,
        from_user_id INTEGER,
        to_user_id INTEGER,
        amount INTEGER,
        transaction_type TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (room_id) REFERENCES rooms(room_id)
    )''')
    
    # Таблица рефералов
    c.execute('''CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_user_id INTEGER,
        referred_user_id INTEGER UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (referrer_user_id) REFERENCES users(user_id),
        FOREIGN KEY (referred_user_id) REFERENCES users(user_id)
    )''')
    
    # Таблица реферальных бонусов
    c.execute('''CREATE TABLE IF NOT EXISTS referral_bonuses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_user_id INTEGER,
        referred_user_id INTEGER,
        bonus_amount INTEGER,
        bonus_type TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (referrer_user_id) REFERENCES users(user_id),
        FOREIGN KEY (referred_user_id) REFERENCES users(user_id)
    )''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def validate_telegram_init_data(init_data: str) -> Optional[Dict]:
    """
    Валидация initData от Telegram WebApp
    Возвращает распарсенные данные пользователя или None если невалидно
    """
    try:
        # Парсинг init_data
        params = {}
        for item in init_data.split('&'):
            key, value = item.split('=', 1)
            params[key] = value
        
        # Получаем hash и удаляем его из параметров
        received_hash = params.pop('hash', None)
        if not received_hash:
            return None
        
        # Проверяем auth_date (не старше 1 часа)
        auth_date = int(params.get('auth_date', 0))
        if time.time() - auth_date > 3600:
            logger.warning("Init data expired")
            return None
        
        # Создаем data_check_string
        data_check_arr = [f"{k}={v}" for k, v in sorted(params.items())]
        data_check_string = '\n'.join(data_check_arr)
        
        # Вычисляем secret_key
        secret_key = hmac.new(
            "WebAppData".encode(),
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()
        
        # Вычисляем hash
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Сравниваем хеши
        if calculated_hash != received_hash:
            logger.warning("Invalid hash")
            return None
        
        # Парсим user данные
        user_data = json.loads(params.get('user', '{}'))
        return user_data
    
    except Exception as e:
        logger.error(f"Error validating init data: {e}")
        return None

def get_or_create_user(user_data: Dict) -> int:
    """Получить или создать пользователя в БД"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    user_id = user_data.get('id')
    username = user_data.get('username', '')
    first_name = user_data.get('first_name', '')
    last_name = user_data.get('last_name', '')
    
    # Проверяем существование
    c.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    if c.fetchone() is None:
        # Создаем нового пользователя
        c.execute('''INSERT INTO users (user_id, username, first_name, last_name)
                     VALUES (?, ?, ?, ?)''',
                  (user_id, username, first_name, last_name))
        conn.commit()
        logger.info(f"Created new user: {user_id}")
    
    conn.close()
    return user_id

def find_or_create_room(entry_fee: int) -> str:
    """Найти доступную комнату или создать новую"""
    with rooms_lock:
        # Ищем незаполненную комнату с таким же entry_fee
        for room_id, room in rooms.items():
            if (room['entry_fee'] == entry_fee and 
                room['status'] == 'waiting' and 
                len(room['participants']) < MAX_ROOM_SIZE):
                return room_id
        
        # Создаем новую комнату
        room_id = secrets.token_urlsafe(16)
        rooms[room_id] = {
            'room_id': room_id,
            'entry_fee': entry_fee,
            'status': 'waiting',  # waiting, drawing, completed
            'participants': [],
            'total_pool': 0,
            'winner': None,
            'created_at': datetime.now().isoformat()
        }
        
        # Сохраняем в БД
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO rooms (room_id, entry_fee, status, total_pool)
                     VALUES (?, ?, ?, ?)''',
                  (room_id, entry_fee, 'waiting', 0))
        conn.commit()
        conn.close()
        
        logger.info(f"Created new room: {room_id} with entry fee: {entry_fee}")
        return room_id

def add_participant_to_room(room_id: str, user_id: int, payment_id: int, user_data: Dict):
    """Добавить участника в комнату"""
    with rooms_lock:
        if room_id not in rooms:
            return False
        
        room = rooms[room_id]
        
        # Проверяем, что пользователь еще не в комнате
        if any(p['user_id'] == user_id for p in room['participants']):
            logger.warning(f"User {user_id} already in room {room_id}")
            return False
        
        # Добавляем участника
        participant = {
            'user_id': user_id,
            'username': user_data.get('username', ''),
            'first_name': user_data.get('first_name', ''),
            'payment_id': payment_id,
            'joined_at': datetime.now().isoformat()
        }
        room['participants'].append(participant)
        room['total_pool'] += room['entry_fee']
        
        # Сохраняем в БД
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO room_participants (room_id, user_id, payment_id)
                     VALUES (?, ?, ?)''',
                  (room_id, user_id, payment_id))
        c.execute('''UPDATE rooms SET total_pool = ? WHERE room_id = ?''',
                  (room['total_pool'], room_id))
        conn.commit()
        conn.close()
        
        logger.info(f"Added user {user_id} to room {room_id}. Participants: {len(room['participants'])}/{MAX_ROOM_SIZE}")
        
        # Если комната заполнена, запускаем розыгрыш
        if len(room['participants']) >= MAX_ROOM_SIZE:
            room['status'] = 'drawing'
            logger.info(f"Room {room_id} is full. Starting lottery...")
        
        return True

def send_stars_to_user(user_id: int, amount: int) -> bool:
    """Отправить Stars пользователю (заглушка - нужна реализация через Bot API)"""
    # TODO: Реализовать отправку Stars через Bot API
    # В текущей версии Bot API нет прямого метода отправки Stars
    # Нужно использовать refundStarPayment или другие методы
    logger.info(f"Would send {amount} Stars to user {user_id}")
    return True

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.route('/api/user/info', methods=['POST'])
def get_user_info():
    """Получить информацию о пользователе"""
    try:
        data = request.json
        init_data = data.get('initData', '')
        
        # Валидация
        user_data = validate_telegram_init_data(init_data)
        if not user_data:
            return jsonify({'error': 'Invalid init data'}), 401
        
        # Получаем или создаем пользователя
        user_id = get_or_create_user(user_data)
        
        # Получаем статистику пользователя
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Количество игр
        c.execute('''SELECT COUNT(*) FROM room_participants WHERE user_id = ?''', (user_id,))
        total_games = c.fetchone()[0]
        
        # Количество побед
        c.execute('''SELECT COUNT(*) FROM rooms WHERE winner_user_id = ?''', (user_id,))
        total_wins = c.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'user_id': user_id,
            'username': user_data.get('username', ''),
            'first_name': user_data.get('first_name', ''),
            'total_games': total_games,
            'total_wins': total_wins
        })
    
    except Exception as e:
        logger.error(f"Error in get_user_info: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/create-invoice', methods=['POST'])
@limiter.limit("10 per minute")
def create_invoice():
    """Создать инвойс для оплаты"""
    try:
        # Валидация входных данных
        schema = CreateInvoiceSchema()
        try:
            validated_data = schema.load(request.json)
        except ValidationError as err:
            return jsonify({'error': err.messages}), 400
        
        init_data = validated_data['initData']
        entry_fee = validated_data['entryFee']
        
        # Валидация Telegram данных
        user_data = validate_telegram_init_data(init_data)
        if not user_data:
            return jsonify({'error': 'Invalid init data'}), 401
        
        user_id = user_data.get('id')
        
        # Создаем инвойс через Bot API
        invoice_data = {
            'title': f'Lottery Entry - {entry_fee} Stars',
            'description': f'Join the lottery room with {MAX_ROOM_SIZE} participants. Winner takes {int(WINNER_PERCENTAGE * 100)}% of the pool!',
            'payload': json.dumps({
                'user_id': user_id,
                'entry_fee': entry_fee,
                'timestamp': int(time.time())
            }),
            'currency': 'XTR',
            'prices': [{'label': 'Entry Fee', 'amount': entry_fee}]
        }
        
        # Отправляем запрос к Bot API
        response = requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/createInvoiceLink',
            json=invoice_data
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                invoice_link = result['result']
                return jsonify({'invoice_link': invoice_link})
        
        logger.error(f"Failed to create invoice: {response.text}")
        return jsonify({'error': 'Failed to create invoice'}), 500
    
    except Exception as e:
        logger.error(f"Error in create_invoice: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/room/<room_id>', methods=['GET'])
def get_room_info(room_id):
    """Получить информацию о комнате"""
    try:
        with rooms_lock:
            if room_id not in rooms:
                return jsonify({'error': 'Room not found'}), 404
            
            room = rooms[room_id]
            return jsonify({
                'room_id': room['room_id'],
                'entry_fee': room['entry_fee'],
                'status': room['status'],
                'participants': room['participants'],
                'total_pool': room['total_pool'],
                'winner': room.get('winner'),
                'max_participants': MAX_ROOM_SIZE
            })
    
    except Exception as e:
        logger.error(f"Error in get_room_info: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/room/<room_id>/stream', methods=['GET'])
def stream_room_updates(room_id):
    """Server-Sent Events для real-time обновлений комнаты"""
    def generate():
        last_update = None
        while True:
            with rooms_lock:
                if room_id not in rooms:
                    yield f"data: {json.dumps({'error': 'Room not found'})}\n\n"
                    break
                
                room = rooms[room_id]
                current_update = json.dumps(room, default=str)
                
                if current_update != last_update:
                    yield f"data: {current_update}\n\n"
                    last_update = current_update
                
                # Если комната завершена, закрываем поток
                if room['status'] == 'completed':
                    break
            
            time.sleep(1)
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook для обработки обновлений от Telegram Bot"""
    try:
        update = request.json
        logger.info(f"Received update: {json.dumps(update)}")
        
        # Обработка pre_checkout_query
        if 'pre_checkout_query' in update:
            query = update['pre_checkout_query']
            query_id = query['id']
            payload = json.loads(query['invoice_payload'])
            
            user_id = payload['user_id']
            entry_fee = payload['entry_fee']
            
            # Проверяем, что пользователь не в активной комнате
            with rooms_lock:
                user_in_active_room = False
                for room in rooms.values():
                    if room['status'] != 'completed':
                        if any(p['user_id'] == user_id for p in room['participants']):
                            user_in_active_room = True
                            break
            
            if user_in_active_room:
                # Отклоняем платеж
                requests.post(
                    f'https://api.telegram.org/bot{BOT_TOKEN}/answerPreCheckoutQuery',
                    json={
                        'pre_checkout_query_id': query_id,
                        'ok': False,
                        'error_message': 'You are already in an active room. Please wait for it to complete.'
                    }
                )
            else:
                # Подтверждаем платеж
                requests.post(
                    f'https://api.telegram.org/bot{BOT_TOKEN}/answerPreCheckoutQuery',
                    json={'pre_checkout_query_id': query_id, 'ok': True}
                )
        
        # Обработка successful_payment
        elif 'message' in update and 'successful_payment' in update['message']:
            message = update['message']
            payment = message['successful_payment']
            user = message['from']
            
            payload = json.loads(payment['invoice_payload'])
            user_id = payload['user_id']
            entry_fee = payload['entry_fee']
            charge_id = payment['telegram_payment_charge_id']
            
            # Сохраняем платеж в БД
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''INSERT INTO payments (user_id, amount, telegram_payment_charge_id, status)
                         VALUES (?, ?, ?, ?)''',
                      (user_id, entry_fee, charge_id, 'completed'))
            payment_id = c.lastrowid
            conn.commit()
            conn.close()
            
            # Находим или создаем комнату
            room_id = find_or_create_room(entry_fee)
            
            # Добавляем участника в комнату
            user_data = {
                'id': user_id,
                'username': user.get('username', ''),
                'first_name': user.get('first_name', '')
            }
            add_participant_to_room(room_id, user_id, payment_id, user_data)
            
            # Обновляем payment с room_id
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('UPDATE payments SET room_id = ? WHERE id = ?', (room_id, payment_id))
            conn.commit()
            conn.close()
            
            # Отправляем сообщение пользователю
            requests.post(
                f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                json={
                    'chat_id': user_id,
                    'text': f'✅ Payment successful! You joined the lottery room.\n\n'
                            f'Entry fee: {entry_fee} ⭐\n'
                            f'Room: {room_id[:8]}...\n'
                            f'Waiting for other participants...'
                }
            )
        
        return jsonify({'ok': True})
    
    except Exception as e:
        logger.error(f"Error in webhook: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/referral/link', methods=['POST'])
@limiter.limit("20 per minute")
def get_referral_link():
    """Получить реферальную ссылку пользователя"""
    try:
        data = request.json
        init_data = data.get('initData', '')
        
        user_data = validate_telegram_init_data(init_data)
        if not user_data:
            return jsonify({'error': 'Invalid init data'}), 401
        
        user_id = user_data.get('id')
        
        # Создаем реферальную ссылку
        bot_username = os.environ.get('BOT_USERNAME', 'your_bot')
        referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        
        # Получаем статистику рефералов
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Количество приглашенных
        c.execute('SELECT COUNT(*) FROM referrals WHERE referrer_user_id = ?', (user_id,))
        total_referrals = c.fetchone()[0]
        
        # Общая сумма бонусов
        c.execute('SELECT COALESCE(SUM(bonus_amount), 0) FROM referral_bonuses WHERE referrer_user_id = ?', (user_id,))
        total_bonuses = c.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'referral_link': referral_link,
            'total_referrals': total_referrals,
            'total_bonuses': total_bonuses
        })
    
    except Exception as e:
        logger.error(f"Error in get_referral_link: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/referral/register', methods=['POST'])
@limiter.limit("5 per hour")
def register_referral():
    """Зарегистрировать реферала"""
    try:
        data = request.json
        init_data = data.get('initData', '')
        referrer_id = data.get('referrerId')
        
        user_data = validate_telegram_init_data(init_data)
        if not user_data:
            return jsonify({'error': 'Invalid init data'}), 401
        
        user_id = user_data.get('id')
        
        if not referrer_id or user_id == referrer_id:
            return jsonify({'error': 'Invalid referrer'}), 400
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Проверяем, что пользователь еще не был приглашен
        c.execute('SELECT id FROM referrals WHERE referred_user_id = ?', (user_id,))
        if c.fetchone():
            conn.close()
            return jsonify({'error': 'User already referred'}), 400
        
        # Проверяем существование реферера
        c.execute('SELECT user_id FROM users WHERE user_id = ?', (referrer_id,))
        if not c.fetchone():
            conn.close()
            return jsonify({'error': 'Referrer not found'}), 404
        
        # Регистрируем реферала
        c.execute('''INSERT INTO referrals (referrer_user_id, referred_user_id)
                     VALUES (?, ?)''', (referrer_id, user_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"User {user_id} registered as referral of {referrer_id}")
        
        return jsonify({
            'success': True,
            'message': 'Referral registered successfully'
        })
    
    except Exception as e:
        logger.error(f"Error in register_referral: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/referral/stats', methods=['POST'])
@limiter.limit("30 per minute")
def get_referral_stats():
    """Получить детальную статистику по рефералам"""
    try:
        data = request.json
        init_data = data.get('initData', '')
        
        user_data = validate_telegram_init_data(init_data)
        if not user_data:
            return jsonify({'error': 'Invalid init data'}), 401
        
        user_id = user_data.get('id')
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Список рефералов с их активностью
        c.execute('''
            SELECT 
                u.user_id,
                u.first_name,
                u.username,
                r.created_at,
                COUNT(rp.id) as games_played,
                COALESCE(SUM(CASE WHEN ro.winner_user_id = u.user_id THEN 1 ELSE 0 END), 0) as wins
            FROM referrals r
            JOIN users u ON r.referred_user_id = u.user_id
            LEFT JOIN room_participants rp ON u.user_id = rp.user_id
            LEFT JOIN rooms ro ON rp.room_id = ro.room_id
            WHERE r.referrer_user_id = ?
            GROUP BY u.user_id, u.first_name, u.username, r.created_at
            ORDER BY r.created_at DESC
            LIMIT 50
        ''', (user_id,))
        
        referrals = []
        for row in c.fetchall():
            referrals.append({
                'user_id': row[0],
                'first_name': row[1],
                'username': row[2],
                'joined_at': row[3],
                'games_played': row[4],
                'wins': row[5]
            })
        
        # Общая статистика бонусов
        c.execute('''
            SELECT bonus_type, SUM(bonus_amount), COUNT(*)
            FROM referral_bonuses
            WHERE referrer_user_id = ?
            GROUP BY bonus_type
        ''', (user_id,))
        
        bonuses_by_type = {}
        for row in c.fetchall():
            bonuses_by_type[row[0]] = {
                'total_amount': row[1],
                'count': row[2]
            }
        
        conn.close()
        
        return jsonify({
            'referrals': referrals,
            'bonuses_by_type': bonuses_by_type
        })
    
    except Exception as e:
        logger.error(f"Error in get_referral_stats: {e}")
        return jsonify({'error': 'Internal server error'}), 500

def setup_webhook():
    """Установить webhook для бота"""
    if not WEBHOOK_URL or not BOT_TOKEN:
        logger.warning("WEBHOOK_URL or BOT_TOKEN not set. Skipping webhook setup.")
        return
    
    webhook_url = f"{WEBHOOK_URL}/webhook"
    response = requests.post(
        f'https://api.telegram.org/bot{BOT_TOKEN}/setWebhook',
        json={'url': webhook_url}
    )
    
    if response.status_code == 200:
        logger.info(f"Webhook set successfully: {webhook_url}")
    else:
        logger.error(f"Failed to set webhook: {response.text}")

if __name__ == '__main__':
    init_db()
    setup_webhook()
    
    # Запускаем планировщик розыгрышей
    from scheduler import start_scheduler
    scheduler = start_scheduler(rooms, rooms_lock, DB_PATH)
    
    # Запускаем бота (если нужен polling mode)
    # from bot import start_bot_polling
    # start_bot_polling()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
