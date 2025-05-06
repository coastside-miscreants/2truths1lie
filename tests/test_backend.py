"""
Unit tests for the Two Truths & AI Game backend server.

These tests verify the functionality of the Flask server, API endpoints,
and core game logic using pytest. Redis-dependent tests use fakeredis for
in-memory testing without requiring a real Redis instance.
"""

import os
import sys
import json
import pytest
import fakeredis
from unittest.mock import patch, MagicMock
import tempfile
import yaml

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# We need to mock important modules before importing the main application
sys.modules['anthropic'] = MagicMock()
sys.modules['redis'] = MagicMock()

# Import the Flask app and other modules
from src.main import app, generate_new_round, get_session_id, update_session_history, get_session_history

@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def mock_redis():
    """Create a mock Redis client using fakeredis."""
    with patch('src.main.redis_client') as mock:
        # Use fakeredis for an in-memory Redis implementation
        mock.return_value = fakeredis.FakeStrictRedis(decode_responses=True)
        yield mock

@pytest.fixture
def mock_anthropic():
    """Create a mock Anthropic client."""
    with patch('src.main.anthropic_client') as mock:
        # Configure the mock to return a sample response
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps({
            "statements": [
                {"text": "Truth statement 1", "isLie": False, "explanation": "Truth explanation 1"},
                {"text": "Truth statement 2", "isLie": False, "explanation": "Truth explanation 2"},
                {"text": "Lie statement", "isLie": True, "explanation": "Lie explanation"}
            ]
        }))]
        mock.messages.create.return_value = mock_message
        yield mock

@pytest.fixture
def config_file():
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as config:
        # Write a test prompt to the config file
        yaml_content = {
            "claude_prompt": "Test prompt for Claude"
        }
        yaml.dump(yaml_content, config)
        config_path = config.name
    
    # Save the original config paths and patch with our temp file
    with patch('src.main.config_paths', [config_path]):
        yield config_path
    
    # Clean up the temp file
    os.unlink(config_path)

def test_index_route(client):
    """Test that the index route returns the index.html file."""
    response = client.get('/')
    assert response.status_code == 200
    # The actual content will depend on index.html, but we can check for basic HTML structure
    assert b'<!DOCTYPE html>' in response.data

def test_trigger_new_round(client, mock_anthropic):
    """Test the /api/trigger_new_round endpoint."""
    # First request should succeed with 200 OK
    response = client.get('/api/trigger_new_round')
    assert response.status_code == 200
    assert json.loads(response.data)['message'] == "New round generation triggered"
    
    # Second request while generation is in progress should return 202 Accepted
    response = client.get('/api/trigger_new_round')
    assert response.status_code == 202
    assert json.loads(response.data)['message'] == "New round generation already requested"

@patch('src.main.current_session_id', 'test-session-id')
def test_session_endpoint_get(client, mock_redis):
    """Test the GET /api/session endpoint."""
    response = client.get('/api/session')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['session_id'] == 'test-session-id'
    assert 'round_count' in data
    assert 'rounds_in_history' in data

@patch('src.main.current_session_id', 'test-session-id')
def test_session_endpoint_post_reset(client, mock_redis):
    """Test the POST /api/session endpoint with reset action."""
    response = client.post('/api/session', 
                          json={'action': 'reset'},
                          content_type='application/json')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'message' in data
    assert 'reset' in data['message']

@patch('src.main.current_session_id', None)
def test_session_endpoint_post_new(client):
    """Test the POST /api/session endpoint with new action."""
    response = client.post('/api/session', 
                          json={'action': 'new'},
                          content_type='application/json')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'message' in data
    assert 'New session created' in data['message']
    assert 'session_id' in data

def test_session_endpoint_post_invalid(client):
    """Test the POST /api/session endpoint with invalid action."""
    response = client.post('/api/session', 
                          json={'action': 'invalid'},
                          content_type='application/json')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

def test_get_session_id():
    """Test the get_session_id function."""
    with patch('src.main.current_session_id', None):
        # First call should generate a new ID
        session_id = get_session_id()
        assert session_id is not None
        assert len(session_id) > 0
        
        # Second call with same state should return the existing ID
        with patch('src.main.current_session_id', session_id):
            session_id2 = get_session_id()
            assert session_id2 == session_id

def test_update_and_get_session_history():
    """Test the update_session_history and get_session_history functions."""
    test_session_id = 'test-session-id'
    test_statements = [
        {"text": "Test truth 1", "isLie": False, "explanation": "Truth explanation"},
        {"text": "Test truth 2", "isLie": False, "explanation": "Truth explanation"},
        {"text": "Test lie", "isLie": True, "explanation": "Lie explanation"}
    ]
    
    # Test with in-memory fallback (redis_client = None)
    with patch('src.main.redis_client', None):
        # Initial state should be empty
        with patch('src.main.session_history', {"rounds": [], "round_count": 0}):
            # Update history
            update_session_history(test_session_id, test_statements)
            
            # Get history and verify
            history = get_session_history(test_session_id)
            assert history["round_count"] == 1
            assert len(history["rounds"]) == 1
            assert history["rounds"][0] == test_statements

def test_generate_new_round(mock_anthropic, config_file):
    """Test the generate_new_round function."""
    # Set up test environment
    with patch('src.main.redis_client', None), \
         patch('src.main.current_session_id', 'test-session-id'), \
         patch('src.main.session_history', {"rounds": [], "round_count": 0}):
        
        # Call function
        result = generate_new_round()
        
        # Verify results
        assert "statements" in result
        assert len(result["statements"]) == 3
        
        # Check that one statement is a lie and two are truths
        lie_count = sum(1 for stmt in result["statements"] if stmt["isLie"])
        truth_count = sum(1 for stmt in result["statements"] if not stmt["isLie"])
        assert lie_count == 1
        assert truth_count == 2

def test_game_stream_endpoint(client):
    """Test the /api/game_stream SSE endpoint."""
    # This is more challenging to test thoroughly without a full integration test
    # But we can check that it returns the correct content type
    response = client.get('/api/game_stream')
    assert response.status_code == 200
    assert response.content_type == 'text/event-stream'
    
# Tests for error handling
def test_generate_new_round_anthropic_error():
    """Test error handling in generate_new_round when Anthropic client fails."""
    with patch('src.main.anthropic_client', None), \
         patch('src.main.claude_prompt', 'Test prompt'):
        result = generate_new_round()
        assert "error" in result
        assert "Anthropic client not initialized" in result["error"]

def test_generate_new_round_no_prompt():
    """Test error handling in generate_new_round when Claude prompt is missing."""
    with patch('src.main.anthropic_client', MagicMock()), \
         patch('src.main.claude_prompt', None):
        result = generate_new_round()
        assert "error" in result
        assert "Claude prompt not loaded" in result["error"]

def test_invalid_static_path(client):
    """Test that attempting to access files outside the static folder fails."""
    response = client.get('/../config.yaml')  # Attempt path traversal
    assert response.status_code == 404
    assert b'Invalid path' in response.data