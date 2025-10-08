import random
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

WINNER_PERCENTAGE = 0.80
ADMIN_PERCENTAGE = 0.20
ADMIN_USERNAME = 'klimaz'

def conduct_lottery(room_id: str, rooms: Dict, db_path: str = 'lottery.db') -> Optional[Dict]:
    """
    Провести розыгрыш в комнате
    Возвращает информацию о победителе
    """
    try:
        if room_id not in rooms:
            logger.error(f"Room {room_id} not found")
            return None
        
        room = rooms[room_id]
        
        if room['status'] != 'drawing':
            logger.warning(f"Room {room_id} is not in drawing status")
            return None
        
        if len(room['participants']) == 0:
            logger.error(f"Room {room_id} has no participants")
            return None
        
        # Выбираем случайного победителя
        winner = random.choice(room['participants'])
        winner_user_id = winner['user_id']
        
        # Рассчитываем суммы
        total_pool = room['total_pool']
        winner_amount = int(total_pool * WINNER_PERCENTAGE)
        admin_amount = total_pool - winner_amount
        
        logger.info(f"Lottery result for room {room_id}:")
        logger.info(f"  Winner: {winner_user_id} ({winner.get('first_name', 'Unknown')})")
        logger.info(f"  Total pool: {total_pool} Stars")
        logger.info(f"  Winner gets: {winner_amount} Stars")
        logger.info(f"  Admin gets: {admin_amount} Stars")
        
        # Обновляем комнату
        room['status'] = 'completed'
        room['winner'] = {
            'user_id': winner_user_id,
            'username': winner.get('username', ''),
            'first_name': winner.get('first_name', ''),
            'amount': winner_amount
        }
        room['completed_at'] = datetime.now().isoformat()
        
        # Сохраняем результат в БД
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Обновляем комнату
        c.execute('''UPDATE rooms 
                     SET status = ?, winner_user_id = ?, completed_at = ?
                     WHERE room_id = ?''',
                  ('completed', winner_user_id, datetime.now(), room_id))
        
        # Записываем транзакции
        # Транзакция выигрыша
        c.execute('''INSERT INTO transactions 
                     (room_id, from_user_id, to_user_id, amount, transaction_type)
                     VALUES (?, ?, ?, ?, ?)''',
                  (room_id, None, winner_user_id, winner_amount, 'winner_payout'))
        
        # Транзакция админу (записываем для аудита, реальная выплата отдельно)
        c.execute('''INSERT INTO transactions 
                     (room_id, from_user_id, to_user_id, amount, transaction_type)
                     VALUES (?, ?, ?, ?, ?)''',
                  (room_id, None, None, admin_amount, 'admin_fee'))
        
        conn.commit()
        conn.close()
        
        return {
            'room_id': room_id,
            'winner': room['winner'],
            'total_pool': total_pool,
            'winner_amount': winner_amount,
            'admin_amount': admin_amount,
            'participants': room['participants']
        }
    
    except Exception as e:
        logger.error(f"Error conducting lottery for room {room_id}: {e}")
        return None

def get_room_statistics(db_path: str = 'lottery.db') -> Dict:
    """Получить общую статистику по всем комнатам"""
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Общее количество комнат
        c.execute('SELECT COUNT(*) FROM rooms')
        total_rooms = c.fetchone()[0]
        
        # Завершенные комнаты
        c.execute("SELECT COUNT(*) FROM rooms WHERE status = 'completed'")
        completed_rooms = c.fetchone()[0]
        
        # Общий пул
        c.execute('SELECT SUM(total_pool) FROM rooms WHERE status = "completed"')
        total_pool = c.fetchone()[0] or 0
        
        # Общее количество участников
        c.execute('SELECT COUNT(*) FROM room_participants')
        total_participants = c.fetchone()[0]
        
        # Общая сумма админских сборов
        c.execute('''SELECT SUM(amount) FROM transactions 
                     WHERE transaction_type = "admin_fee"''')
        total_admin_fees = c.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'total_rooms': total_rooms,
            'completed_rooms': completed_rooms,
            'total_pool': total_pool,
            'total_participants': total_participants,
            'total_admin_fees': total_admin_fees
        }
    
    except Exception as e:
        logger.error(f"Error getting room statistics: {e}")
        return {}

def get_user_statistics(user_id: int, db_path: str = 'lottery.db') -> Dict:
    """Получить статистику пользователя"""
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Количество игр
        c.execute('SELECT COUNT(*) FROM room_participants WHERE user_id = ?', (user_id,))
        total_games = c.fetchone()[0]
        
        # Количество побед
        c.execute('SELECT COUNT(*) FROM rooms WHERE winner_user_id = ?', (user_id,))
        total_wins = c.fetchone()[0]
        
        # Общая сумма выигрышей
        c.execute('''SELECT SUM(amount) FROM transactions 
                     WHERE to_user_id = ? AND transaction_type = "winner_payout"''',
                  (user_id,))
        total_winnings = c.fetchone()[0] or 0
        
        # Общая сумма потраченных Stars
        c.execute('''SELECT SUM(amount) FROM payments 
                     WHERE user_id = ? AND status = "completed"''',
                  (user_id,))
        total_spent = c.fetchone()[0] or 0
        
        conn.close()
        
        win_rate = (total_wins / total_games * 100) if total_games > 0 else 0
        
        return {
            'total_games': total_games,
            'total_wins': total_wins,
            'win_rate': round(win_rate, 2),
            'total_winnings': total_winnings,
            'total_spent': total_spent,
            'net_profit': total_winnings - total_spent
        }
    
    except Exception as e:
        logger.error(f"Error getting user statistics for {user_id}: {e}")
        return {}

def cleanup_old_rooms(rooms: Dict, max_age_hours: int = 24):
    """Очистить старые незавершенные комнаты"""
    try:
        from datetime import datetime, timedelta
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        rooms_to_remove = []
        
        for room_id, room in rooms.items():
            if room['status'] != 'completed':
                created_at = datetime.fromisoformat(room['created_at'])
                if created_at < cutoff_time:
                    rooms_to_remove.append(room_id)
        
        for room_id in rooms_to_remove:
            logger.info(f"Removing old room: {room_id}")
            del rooms[room_id]
        
        return len(rooms_to_remove)
    
    except Exception as e:
        logger.error(f"Error cleaning up old rooms: {e}")
        return 0
