import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app as flask_app

@pytest.fixture
def app():
    """Create application for testing"""
    flask_app.config['TESTING'] = True
    return flask_app

@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()

def test_health_check(client):
    """Test health check endpoint"""
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json['status'] == 'ok'

def test_user_info_missing_data(client):
    """Test user info endpoint with missing data"""
    response = client.post('/api/user/info', json={})
    assert response.status_code == 400

def test_create_invoice_missing_data(client):
    """Test create invoice endpoint with missing data"""
    response = client.post('/api/create-invoice', json={})
    assert response.status_code == 400

def test_create_invoice_invalid_entry_fee(client):
    """Test create invoice with invalid entry fee"""
    response = client.post('/api/create-invoice', json={
        'initData': 'test_data',
        'entryFee': 999  # Invalid entry fee
    })
    assert response.status_code == 400

def test_room_not_found(client):
    """Test getting non-existent room"""
    response = client.get('/api/room/non_existent_room')
    assert response.status_code == 404

def test_webhook_missing_data(client):
    """Test webhook endpoint with missing data"""
    response = client.post('/webhook', json={})
    # Should return 200 even with invalid data (Telegram requirement)
    assert response.status_code == 200
