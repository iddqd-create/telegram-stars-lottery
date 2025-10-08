import time
import logging
from threading import Thread
from lottery_engine import conduct_lottery
from bot import notify_room_participants

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LotteryScheduler:
    """Планировщик для автоматического проведения розыгрышей"""
    
    def __init__(self, rooms, rooms_lock, db_path='lottery.db'):
        self.rooms = rooms
        self.rooms_lock = rooms_lock
        self.db_path = db_path
        self.running = False
    
    def start(self):
        """Запустить планировщик"""
        if self.running:
            logger.warning("Scheduler already running")
            return
        
        self.running = True
        thread = Thread(target=self._run, daemon=True)
        thread.start()
        logger.info("Lottery scheduler started")
    
    def stop(self):
        """Остановить планировщик"""
        self.running = False
        logger.info("Lottery scheduler stopped")
    
    def _run(self):
        """Основной цикл планировщика"""
        while self.running:
            try:
                self._check_and_conduct_lotteries()
                time.sleep(5)  # Проверяем каждые 5 секунд
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(5)
    
    def _check_and_conduct_lotteries(self):
        """Проверить комнаты и провести розыгрыши"""
        with self.rooms_lock:
            rooms_to_draw = []
            
            # Находим комнаты готовые к розыгрышу
            for room_id, room in self.rooms.items():
                if room['status'] == 'drawing':
                    # Проверяем, прошло ли достаточно времени для анимации
                    # В реальности можно добавить задержку для анимации
                    rooms_to_draw.append(room_id)
            
            # Проводим розыгрыши
            for room_id in rooms_to_draw:
                logger.info(f"Conducting lottery for room {room_id}")
                result = conduct_lottery(room_id, self.rooms, self.db_path)
                
                if result:
                    # Отправляем уведомления участникам
                    try:
                        notify_room_participants(result)
                    except Exception as e:
                        logger.error(f"Error notifying participants: {e}")
                else:
                    logger.error(f"Failed to conduct lottery for room {room_id}")

def start_scheduler(rooms, rooms_lock, db_path='lottery.db'):
    """Создать и запустить планировщик"""
    scheduler = LotteryScheduler(rooms, rooms_lock, db_path)
    scheduler.start()
    return scheduler
