import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lottery_engine import conduct_lottery

def test_conduct_lottery():
    """Test basic lottery functionality"""
    rooms = {
        'test_room': {
            'room_id': 'test_room',
            'entry_fee': 100,
            'status': 'drawing',
            'participants': [
                {'user_id': 1, 'first_name': 'User1', 'payment_id': 1},
                {'user_id': 2, 'first_name': 'User2', 'payment_id': 2},
                {'user_id': 3, 'first_name': 'User3', 'payment_id': 3},
                {'user_id': 4, 'first_name': 'User4', 'payment_id': 4},
                {'user_id': 5, 'first_name': 'User5', 'payment_id': 5},
                {'user_id': 6, 'first_name': 'User6', 'payment_id': 6},
            ],
            'total_pool': 600
        }
    }
    
    result = conduct_lottery('test_room', rooms, ':memory:')
    
    assert result is not None
    assert 'winner' in result
    assert result['winner']['user_id'] in [1, 2, 3, 4, 5, 6]
    assert result['winner_amount'] == 480  # 80% of 600
    assert result['admin_amount'] == 120   # 20% of 600
    assert result['room_id'] == 'test_room'

def test_conduct_lottery_different_entry_fee():
    """Test lottery with different entry fee"""
    rooms = {
        'test_room_250': {
            'room_id': 'test_room_250',
            'entry_fee': 250,
            'status': 'drawing',
            'participants': [
                {'user_id': i, 'first_name': f'User{i}', 'payment_id': i}
                for i in range(1, 7)
            ],
            'total_pool': 1500
        }
    }
    
    result = conduct_lottery('test_room_250', rooms, ':memory:')
    
    assert result is not None
    assert result['winner_amount'] == 1200  # 80% of 1500
    assert result['admin_amount'] == 300    # 20% of 1500

def test_conduct_lottery_winner_selection():
    """Test that winner is randomly selected from participants"""
    winners = set()
    
    for _ in range(50):  # Run 50 times to test randomness
        rooms = {
            'test_room': {
                'room_id': 'test_room',
                'entry_fee': 100,
                'status': 'drawing',
                'participants': [
                    {'user_id': i, 'first_name': f'User{i}', 'payment_id': i}
                    for i in range(1, 7)
                ],
                'total_pool': 600
            }
        }
        
        result = conduct_lottery('test_room', rooms, ':memory:')
        winners.add(result['winner']['user_id'])
    
    # With 50 runs, we should see at least 3 different winners (statistically)
    assert len(winners) >= 3

def test_conduct_lottery_invalid_room():
    """Test lottery with non-existent room"""
    rooms = {}
    result = conduct_lottery('non_existent_room', rooms, ':memory:')
    assert result is None

def test_conduct_lottery_wrong_status():
    """Test lottery with room in wrong status"""
    rooms = {
        'test_room': {
            'room_id': 'test_room',
            'entry_fee': 100,
            'status': 'waiting',  # Wrong status
            'participants': [
                {'user_id': i, 'first_name': f'User{i}', 'payment_id': i}
                for i in range(1, 7)
            ],
            'total_pool': 600
        }
    }
    
    result = conduct_lottery('test_room', rooms, ':memory:')
    assert result is None
