"""
Integration tests for the Two Truths & AI Game.

These tests verify the full application flow, including server-client interactions.
They require a running server instance and use Selenium for browser automation.
"""

import os
import sys
import time
import pytest
import subprocess
import threading
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the Flask app
from src.main import app

# Configuration
PORT = 5000
SERVER_URL = f"http://localhost:{PORT}"

@pytest.fixture(scope="module")
def server():
    """Start a test server in a separate thread for integration tests."""
    # Configure the app for testing
    app.config['TESTING'] = True
    
    # Run the server in a separate thread
    def run_server():
        app.run(host="localhost", port=PORT, debug=False, use_reloader=False)
    
    # Start server thread
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    
    # Wait for server to start
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{SERVER_URL}/")
            if response.status_code == 200:
                break
        except requests.exceptions.ConnectionError:
            if attempt == max_attempts - 1:
                pytest.fail("Server failed to start")
            time.sleep(1)
    
    yield SERVER_URL
    
    # No need to explicitly stop the server as it's in a daemon thread

@pytest.fixture(scope="module")
def browser():
    """Set up and tear down a browser for UI testing."""
    # Configure Chrome options
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--headless")  # Run headless for CI environments
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Create the Chrome WebDriver
    try:
        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=chrome_options
        )
    except Exception as e:
        pytest.skip(f"Could not create Chrome WebDriver: {e}")
    
    driver.set_window_size(1280, 720)
    
    yield driver
    
    # Quit the browser
    driver.quit()

@pytest.mark.integration
@pytest.mark.slow
def test_game_flow(server, browser):
    """Test the full game flow from loading to playing a round."""
    # Navigate to the game URL
    browser.get(server)
    
    # Wait for the game to load
    WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, "game-title"))
    )
    
    # Verify that the page title is correct
    assert "2 Truths & AI" in browser.title
    
    # Wait for statements to load (either through loading or actual statements)
    WebDriverWait(browser, 30).until(
        EC.presence_of_element_located((By.CLASS_NAME, "statement-button"))
    )
    
    # Find all statement buttons
    statement_buttons = browser.find_elements(By.CLASS_NAME, "statement-button")
    
    # Verify that there are exactly 3 statements
    assert len(statement_buttons) == 3, f"Expected 3 statements, got {len(statement_buttons)}"
    
    # Click the first statement button
    statement_buttons[0].click()
    
    # Wait for feedback to appear
    WebDriverWait(browser, 10).until(
        EC.visibility_of_element_located((By.ID, "feedback-area"))
    )
    
    # Verify that feedback is shown
    feedback_text = browser.find_element(By.ID, "feedback-text").text
    assert "Correct" in feedback_text or "Incorrect" in feedback_text
    
    # Verify that explanations are shown
    explanations = browser.find_elements(By.CSS_SELECTOR, "#explanations p")
    assert len(explanations) == 3
    
    # Verify that the next round button is visible
    next_round_button = browser.find_element(By.ID, "next-round-button")
    assert next_round_button.is_displayed()
    
    # Verify that the score has been updated
    score_text = browser.find_element(By.CLASS_NAME, "score-board").text
    assert "1 Correct" in score_text or "1 Incorrect" in score_text
    assert "1 Rounds" in score_text

@pytest.mark.integration
def test_api_endpoints(server):
    """Test API endpoints directly."""
    # Test the trigger_new_round endpoint
    response = requests.get(f"{server}/api/trigger_new_round")
    assert response.status_code == 200
    assert "triggered" in response.json()["message"]
    
    # Test the session endpoint
    response = requests.get(f"{server}/api/session")
    assert response.status_code == 200
    assert "session_id" in response.json()
    
    # Test the game_stream endpoint
    # This is hard to test directly with requests as it's an SSE endpoint
    response = requests.get(f"{server}/api/game_stream", stream=True)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/event-stream"