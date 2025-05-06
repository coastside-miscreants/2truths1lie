# src/main.py
"""
Two Truths & AI Game - Backend Server

This module implements a Flask web server that hosts a "2 Truths and a Lie" game
powered by Anthropic's Claude LLM. The server handles:
- LLM interactions to generate game rounds
- Server-Sent Events (SSE) for real-time game updates
- Session management with Redis or in-memory fallback
- Background processing and preloading for performance optimization
- Static file serving for the web frontend

The game presents players with three statements (two true, one false) and
challenges them to identify which statement is the lie.
"""

import os
import sys
import json
import time
import logging
import re  # Regular expressions for JSON extraction
import yaml  # Import YAML library for configuration
import uuid  # For generating unique session IDs
from threading import Lock, Thread
from queue import Queue, Empty
from datetime import datetime # For timestamps in logs and data storage

from flask import Flask, Response, jsonify, send_from_directory, request
import anthropic  # Anthropic API client for Claude LLM
import redis  # Redis for persistent session history

# Ensure the src directory is in the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# --- Configuration & Initialization ---
# Configure logging with timestamps for better debugging
logging.basicConfig(level=logging.INFO, format="%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logging.info("Logging configured with timestamp format.")

# Initialize Flask application with static file serving
app = Flask(__name__, static_folder="static")

# Initialize Redis connection for persistent session storage
# Falls back to in-memory storage if Redis is unavailable
redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_port = int(os.getenv('REDIS_PORT', 6379))
try:
    # Connect to Redis with decoded responses (strings instead of bytes)
    redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    redis_client.ping()  # Test the connection
    logging.info(f"Connected to Redis at {redis_host}:{redis_port}")
except redis.ConnectionError as e:
    logging.warning(f"Could not connect to Redis at {redis_host}:{redis_port}: {e}")
    logging.warning("Falling back to in-memory storage for session history")
    redis_client = None

# Load Anthropic API Key from environment variables
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
if not anthropic_api_key:
    logging.warning("ANTHROPIC_API_KEY environment variable not set. API calls will fail.")
    anthropic_api_key = "placeholder_key"
else:
    logging.info("ANTHROPIC_API_KEY loaded from environment.")

# Load Claude Prompt from YAML configuration file
# The prompt defines how Claude generates game rounds
claude_prompt = ""
config_paths = [
    "/app/config.yaml",                                          # Docker container path
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")  # Local development path
]

# Try loading from multiple possible locations
config_loaded = False
for config_path in config_paths:
    try:
        logging.info(f"Attempting to load config.yaml from {config_path}")
        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f)
            claude_prompt = config_data.get("claude_prompt")
            if not claude_prompt:
                logging.error("claude_prompt not found or empty in config.yaml")
            else:
                logging.info(f"Claude prompt loaded successfully from {config_path}")
                config_loaded = True
                break  # Exit the loop once successfully loaded
    except FileNotFoundError:
        logging.warning(f"{config_path} not found, trying next location...")
    except yaml.YAMLError as e:
        logging.error(f"Error parsing config.yaml at {config_path}: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred loading config.yaml from {config_path}: {e}")

if not config_loaded:
    logging.error("Failed to load config.yaml from any location. Please check that the file exists.")

# Initialize Anthropic Client for API interactions
anthropic_client = None
if anthropic_api_key != "placeholder_key":
    try:
        logging.info("Initializing Anthropic client...")
        anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)
        logging.info("Anthropic client initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize Anthropic client: {e}")
else:
    logging.warning("Anthropic client not initialized due to missing API key.")

# --- Server-Sent Events (SSE) Setup ---
# SSE enables real-time updates from server to client without page refresh
message_queues = {}  # Stores a queue for each connected client
lock = Lock()  # Thread synchronization for message_queues access
preload_lock = Lock()  # Lock for preloaded round access
history_lock = Lock()  # Lock for session history access
new_round_requested = False  # Flag to trigger new round generation
preloaded_round = None  # Cache for a preloaded round to improve response time
is_preloading = False  # Flag to prevent multiple preloading threads

# Redis configuration for persistent session storage
REDIS_SESSION_PREFIX = "twotruths:session:"  # Prefix for session metadata
REDIS_STATEMENT_PREFIX = "twotruths:statements:"  # Prefix for game statements
REDIS_MAX_HISTORY = 100  # Maximum number of rounds to keep in history
REDIS_SESSION_EXPIRY = 60 * 60 * 24 * 30  # 30 days in seconds

# Default in-memory session history as fallback when Redis is unavailable
session_history = {
    "rounds": [],  # List of previous rounds' data
    "round_count": 0  # Counter for total rounds generated
}

# Current session ID (generated or retrieved on first request)
current_session_id = None

# --- Session Management Functions ---

def get_session_id():
    """
    Get or create a unique session ID for the current game session.
    
    The session ID is used to track a player's history across multiple rounds.
    If no session exists, a new UUID is generated.
    
    Returns:
        str: The current session ID
    """
    global current_session_id
    
    if current_session_id:
        return current_session_id
    
    # Generate a new session ID
    new_id = str(uuid.uuid4())
    current_session_id = new_id
    logging.info(f"Created new session ID: {new_id}")
    return new_id

def get_session_history(session_id):
    """
    Retrieve session history from Redis or in-memory fallback.
    
    This function gets the complete game history for a specific session,
    including all previous rounds and statements.
    
    Args:
        session_id (str): The session identifier
        
    Returns:
        dict: A dictionary containing session history with keys:
            - round_count: Total number of rounds played
            - rounds: List of statement sets from previous rounds
    """
    if not redis_client:
        # Use in-memory fallback when Redis is unavailable
        with history_lock:
            return session_history.copy()
    
    try:
        # Get session data from Redis
        session_key = f"{REDIS_SESSION_PREFIX}{session_id}"
        session_data = redis_client.hgetall(session_key)
        
        if not session_data:
            # Initialize new session if it doesn't exist
            session_data = {"round_count": "0"}
            redis_client.hset(session_key, mapping=session_data)
            redis_client.expire(session_key, REDIS_SESSION_EXPIRY)
        
        # Get statement history (previous rounds)
        statements_key = f"{REDIS_STATEMENT_PREFIX}{session_id}"
        statement_history = redis_client.lrange(statements_key, 0, REDIS_MAX_HISTORY - 1)
        
        # Convert to the same format as in-memory history
        history = {
            "round_count": int(session_data.get("round_count", 0)),
            "rounds": []
        }
        
        # Parse each JSON string in the list
        for statement_json in statement_history:
            try:
                statement_data = json.loads(statement_json)
                history["rounds"].append(statement_data)
            except json.JSONDecodeError:
                logging.error(f"Failed to decode statement JSON: {statement_json}")
        
        return history
    except Exception as e:
        logging.error(f"Error retrieving session from Redis: {e}")
        # Fall back to in-memory history on error
        with history_lock:
            return session_history.copy()

def update_session_history(session_id, statements):
    """
    Update session history with a new round of statements.
    
    This function adds a new set of statements to either the Redis store
    or the in-memory fallback, and updates the round counter.
    
    Args:
        session_id (str): The session identifier
        statements (list): List of statement objects from the current round
    """
    if not redis_client:
        # Use in-memory fallback when Redis is unavailable
        with history_lock:
            session_history["rounds"].append(statements)
            session_history["round_count"] += 1
            # Keep only the most recent rounds to limit memory usage
            if len(session_history["rounds"]) > REDIS_MAX_HISTORY:
                session_history["rounds"] = session_history["rounds"][-REDIS_MAX_HISTORY:]
        return
    
    try:
        # Update Redis session
        session_key = f"{REDIS_SESSION_PREFIX}{session_id}"
        statements_key = f"{REDIS_STATEMENT_PREFIX}{session_id}"
        
        # Increment round count
        new_count = redis_client.hincrby(session_key, "round_count", 1)
        redis_client.expire(session_key, REDIS_SESSION_EXPIRY)  # Refresh expiry
        
        # Add new statements to the history (at the beginning for LIFO order)
        statements_json = json.dumps(statements)
        redis_client.lpush(statements_key, statements_json)
        redis_client.ltrim(statements_key, 0, REDIS_MAX_HISTORY - 1)  # Keep only recent history
        redis_client.expire(statements_key, REDIS_SESSION_EXPIRY)  # Refresh expiry
        
        logging.info(f"Updated Redis session {session_id}, round {new_count}, history size: {redis_client.llen(statements_key)}")
    except Exception as e:
        logging.error(f"Error updating Redis session: {e}")
        # Fall back to in-memory history on error
        with history_lock:
            session_history["rounds"].append(statements)
            session_history["round_count"] += 1
            if len(session_history["rounds"]) > REDIS_MAX_HISTORY:
                session_history["rounds"] = session_history["rounds"][-REDIS_MAX_HISTORY:]

def generate_new_round():
    """
    Generate a new game round using the Anthropic Claude LLM.
    
    This function:
    1. Retrieves session history to provide context to Claude
    2. Constructs a prompt with previous rounds to ensure topic diversity
    3. Makes an API call to the Anthropic Claude LLM
    4. Processes and parses the response into a usable game round
    5. Stores the round in the session history
    
    The generated round contains 3 statements (2 true, 1 false) with explanations.
    On every third round, an easter egg about specific characters is included.
    
    Returns:
        dict: A dictionary containing the round data with statements, or an error message
    """
    global new_round_requested
    start_time = time.time()
    logging.info("[generate_new_round] START")
    
    # Validate prerequisites
    if not anthropic_client:
        logging.error("[generate_new_round] Anthropic client not initialized.")
        return {"error": "Anthropic client not initialized. Check API key."}
    if not claude_prompt:
        logging.error("[generate_new_round] Claude prompt is not loaded.")
        return {"error": "Claude prompt not loaded. Check config.yaml."}

    # Get current session ID and history
    session_id = get_session_id()
    history = get_session_history(session_id)
    round_number = history["round_count"] + 1
    history_text = ""
    
    # Prepare history context for Claude to ensure statement diversity
    if len(history["rounds"]) > 0:
        history_text = "Here are the previous statements used in this session:\n"
        # Only use the most recent 15 rounds to keep context manageable
        recent_rounds = history["rounds"][:15]
        for idx, prev_round in enumerate(recent_rounds):
            round_idx = history["round_count"] - len(recent_rounds) + idx + 1
            history_text += f"Round {round_idx}:\n"
            for stmt in prev_round:
                is_lie = stmt.get("isLie", False)
                history_text += f"- {'LIE' if is_lie else 'TRUTH'}: {stmt.get('text', 'Unknown')}\n"
        history_text += f"\nIMPORTANT: You've now seen {len(recent_rounds)} previous rounds. Please generate completely new statements that don't overlap with ANY previous topics or facts."

    try:
        # Determine if this set should include easter eggs (every third set)
        easter_egg_set = (round_number % 3 == 0)
        easter_egg_instruction = ""
        if easter_egg_set:
            easter_egg_instruction = "\n\nIMPORTANT: This is set number " + str(round_number) + ", which is divisible by 3. PLEASE INCLUDE AN EASTER EGG about Erin and John Poore as described in instruction #7."
        
        # Construct the complete prompt with history context
        if history_text:
            # Add a strong instruction to avoid repeating statements
            prompt_to_send = f"{claude_prompt}\n\n{history_text}\n\nIMPORTANT: DO NOT repeat any of the facts or topics above. This is round {round_number}, so ensure complete variety.{easter_egg_instruction}"
        else:
            prompt_to_send = f"{claude_prompt}\n\nThis is round {round_number}.{easter_egg_instruction}"
            
        logging.info(f"[generate_new_round] Sending request to Anthropic API for round {round_number}...")
        logging.debug(f"[generate_new_round] History context length: {len(history_text)} chars")
        
        # Log the prompt for debugging and historical reference
        prompt_log = {
            "round_number": round_number,
            "prompt": claude_prompt,
            "history_context": history_text if history_text else None,
            "full_prompt": prompt_to_send,
            "is_easter_egg_set": easter_egg_set,
            "timestamp": datetime.now().isoformat()
        }
        
        # Store prompt log in Redis if available
        if redis_client:
            try:
                prompt_key = f"{REDIS_SESSION_PREFIX}{session_id}:prompts"
                prompt_json = json.dumps(prompt_log)
                redis_client.lpush(prompt_key, prompt_json)
                redis_client.ltrim(prompt_key, 0, REDIS_MAX_HISTORY - 1)  # Keep only recent history
                redis_client.expire(prompt_key, REDIS_SESSION_EXPIRY)  # Set expiry
                logging.info(f"[generate_new_round] Stored prompt for round {round_number} in Redis")
            except Exception as e:
                logging.error(f"[generate_new_round] Failed to store prompt in Redis: {e}")
        else:
            logging.info(f"[generate_new_round] Redis not available, skipping prompt storage")
        
        # Make the API call to Claude
        api_start_time = time.time()
        message = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20240620",  # Using Claude 3.5 Sonnet for high quality responses
            max_tokens=1000,  # Allow enough tokens for complete responses
            temperature=0.7,  # Moderate creativity to ensure both variety and factual accuracy
            messages=[{"role": "user", "content": prompt_to_send}]
        )
        api_end_time = time.time()
        logging.info(f"[generate_new_round] Received response from Anthropic API. Duration: {api_end_time - api_start_time:.3f}s")
        
        # Extract the text response from Claude
        response_text = message.content[0].text
        
        # Log the response for debugging (truncated if very long)
        if len(response_text) > 500:
            logging.info(f"[generate_new_round] Raw response from Claude (truncated): {response_text[:250]}...{response_text[-250:]}")
        else:
            logging.info(f"[generate_new_round] Raw response from Claude: {response_text}")
        
        # Log the complete response for historical reference
        response_log = {
            "round_number": round_number,
            "response": response_text,
            "timestamp": datetime.now().isoformat()
        }
        
        # Store response log in Redis if available
        if redis_client:
            try:
                response_key = f"{REDIS_SESSION_PREFIX}{session_id}:responses"
                response_json = json.dumps(response_log)
                redis_client.lpush(response_key, response_json)
                redis_client.ltrim(response_key, 0, REDIS_MAX_HISTORY - 1)  # Keep only recent history
                redis_client.expire(response_key, REDIS_SESSION_EXPIRY)  # Set expiry
                logging.info(f"[generate_new_round] Stored response for round {round_number} in Redis")
            except Exception as e:
                logging.error(f"[generate_new_round] Failed to store response in Redis: {e}")
        else:
            logging.info(f"[generate_new_round] Redis not available, skipping response storage")
        
        # Process the response: extract and parse the JSON
        try:
            # Step 1: Try to extract the JSON - Claude sometimes adds text before/after JSON
            # First, look for code blocks which often contain the JSON
            code_block_pattern = r"```(?:json)?(.*?)```"
            code_blocks = re.findall(code_block_pattern, response_text, re.DOTALL)
            
            if code_blocks:
                # Use the last code block if multiple are found (Claude sometimes explains before giving final answer)
                potential_json = code_blocks[-1].strip()
                logging.info(f"[generate_new_round] Extracted JSON from code block: {potential_json[:50]}...")
            else:
                # If no code blocks, try to extract based on braces
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                
                if json_start >= 0 and json_end > json_start:
                    # Extract just the JSON portion
                    potential_json = response_text[json_start:json_end]
                    logging.info(f"[generate_new_round] Extracted JSON using brace boundaries (chars {json_start} to {json_end}).")
                else:
                    potential_json = response_text
                    logging.warning("[generate_new_round] Could not identify clear JSON boundaries in response.")
            
            # Step 2: Parse the JSON, handling common format issues
            try:
                # First try direct parsing
                json_text = potential_json
                round_data = json.loads(json_text)
            except json.JSONDecodeError as e:
                logging.warning(f"[generate_new_round] Initial JSON parsing failed: {e}. Attempting to clean up the JSON.")
                
                # Try to clean up potential issues
                # Remove any leading/trailing whitespace or non-JSON characters
                cleaned_json = potential_json.strip()
                
                # Sometimes Claude escapes quotes when it shouldn't
                if cleaned_json.find('\\"') >= 0:
                    cleaned_json = cleaned_json.replace('\\"', '"')
                    logging.info("[generate_new_round] Removed escaped quotes in JSON.")
                
                # Try again with cleaned JSON
                json_text = cleaned_json
            
            # Parse the final JSON content
            parse_start_time = time.time()
            round_data = json.loads(json_text)
            parse_end_time = time.time()
            logging.info(f"[generate_new_round] Successfully parsed round data. Duration: {parse_end_time - parse_start_time:.3f}s")
            
            # Extract just the statements to store in history
            statements = []
            if "statements" in round_data:
                statements = round_data["statements"]
            
            # Update Redis or in-memory session history
            session_id = get_session_id()
            update_session_history(session_id, statements)
            
            # Log statement topics for better debugging of diversity
            topics = []
            for stmt in statements:
                # Extract a simple topic identifier from the first few words
                text = stmt.get("text", "")
                topic = text.split(" ")[:3]  # Use first 3 words as topic identifier
                topics.append(" ".join(topic) + "...")
            
            logging.info(f"[generate_new_round] Round {round_number} statement topics: {topics}")
            
            # Log Redis session size if available
            if redis_client:
                try:
                    statements_key = f"{REDIS_STATEMENT_PREFIX}{session_id}"
                    history_size = redis_client.llen(statements_key)
                    logging.info(f"[generate_new_round] Redis session {session_id} now has {history_size} rounds in history.")
                except Exception as e:
                    logging.error(f"[generate_new_round] Error getting Redis session size: {e}")
            
            return round_data
        except json.JSONDecodeError as e:
            logging.error(f"[generate_new_round] Failed to parse JSON: {e}")
            logging.error(f"[generate_new_round] Raw response text: {response_text}")
            return {"error": f"Failed to parse response from LLM: {e}"}

    # Handle various API error scenarios
    except anthropic.APIConnectionError as e:
        logging.error(f"[generate_new_round] API connection error: {e}")
        return {"error": f"API Connection Error: {e}"}
    except anthropic.RateLimitError as e:
        logging.error(f"[generate_new_round] API rate limit exceeded: {e}")
        return {"error": f"API Rate Limit Error: {e}"}
    except anthropic.AuthenticationError as e:
        logging.error(f"[generate_new_round] API authentication error: {e}")
        return {"error": f"API Authentication Error: {e}. Check your API key."}
    except anthropic.APIStatusError as e:
        logging.error(f"[generate_new_round] API status error: {e.status_code} - {e.response}")
        return {"error": f"API Status Error: {e.status_code}"}
    except Exception as e:
        logging.error(f"[generate_new_round] Unexpected error during API call: {e}")
        return {"error": f"Unexpected API Error: {e}"}
    finally:
        end_time = time.time()
        logging.info(f"[generate_new_round] END. Total duration: {end_time - start_time:.3f}s")
        # Resetting flag moved to background_task after broadcast

def broadcast_message(event_type, payload):
    """
    Send a message to all connected SSE clients.
    
    This function formats the data as a Server-Sent Event (SSE) message
    and places it in the queues of all connected clients. Each client's
    SSE connection will then receive and process the message.
    
    Args:
        event_type (str): Type of event ('new_round' or 'error')
        payload (dict): Data to send to clients
    """
    logging.info(f"[broadcast_message] Preparing to broadcast event type \"{event_type}\"")
    
    # Format the message according to the event type
    message_data = {"type": event_type}
    if event_type == "error":
        message_data["message"] = payload.get("message", "Unknown error")
    else:
        message_data["payload"] = payload

    # Broadcast to all connected clients
    with lock:
        client_count = len(message_queues)
        logging.info(f"[broadcast_message] Acquiring lock. Broadcasting to {client_count} clients.")
        
        if client_count == 0:
            logging.warning("[broadcast_message] No clients connected to receive message!")
        
        for client_id, queue in message_queues.items():
            try:
                # Format as SSE message: "data: {json}\n\n"
                json_data = json.dumps(message_data)
                msg = f"data: {json_data}\n\n"
                logging.info(f"[broadcast_message] Putting message for client {client_id} into queue.")
                queue.put(msg)
            except TypeError as e:
                logging.error(f"[broadcast_message] Failed to serialize data for client {client_id}, event \"{event_type}\": {e}")
                logging.error(f"[broadcast_message] Data causing error: {message_data}")
        logging.info("[broadcast_message] Releasing lock.")
    logging.info(f"[broadcast_message] Finished broadcasting event type \"{event_type}\"")

def background_task():
    """
    Background thread that manages game round generation and preloading.
    
    This thread runs continuously and:
    1. Checks for new round requests from clients
    2. Uses preloaded rounds when available for faster response
    3. Generates new rounds as needed
    4. Broadcasts rounds to all connected clients
    5. Manages the preloading of future rounds for performance
    
    The thread uses thread-safe mechanisms (locks) to coordinate
    access to shared state between multiple threads.
    """
    global new_round_requested, preloaded_round, is_preloading
    logging.info("[background_task] Starting background thread.")
    
    while True:
        local_new_round_requested = False
        local_preloaded_round = None
        
        # Safely check and update flags using thread locks
        with lock:
            if new_round_requested:
                local_new_round_requested = True
                
        # Process new round requests
        if local_new_round_requested:
            logging.info("[background_task] Flag new_round_requested is TRUE. Processing...")
            
            # First try to use a preloaded round if available
            with preload_lock:
                if preloaded_round:
                    logging.info("[background_task] Using preloaded round data.")
                    local_preloaded_round = preloaded_round
                    preloaded_round = None  # Clear the preloaded round
            
            # Determine round data source (preloaded or new generation)
            if local_preloaded_round:
                round_data = local_preloaded_round
            else:
                logging.info("[background_task] No preloaded round available, generating new round...")
                round_data = generate_new_round()  # This logs its own duration
            
            # Process and broadcast the round data to clients
            if isinstance(round_data, dict) and "error" in round_data:
                logging.error(f"[background_task] Round generation failed: {round_data['error']}")
                
                # Handle preloaded round failure by trying again
                if local_preloaded_round:
                    logging.error("[background_task] Preloaded round had an error. Trying to generate a new round directly.")
                    # Skip the preloaded round and generate a new one directly
                    round_data = generate_new_round()
                    
                    # Check the result of the direct generation
                    if isinstance(round_data, dict) and "error" in round_data:
                        # If direct generation also fails, report the error
                        logging.error(f"[background_task] Direct round generation also failed: {round_data['error']}")
                        broadcast_message("error", {"message": round_data["error"]})
                    elif round_data:
                        # Direct generation succeeded
                        logging.info("[background_task] Direct round generation successful. Broadcasting...")
                        broadcast_message("new_round", round_data)
                    else:
                        logging.error("[background_task] Direct round generation returned unexpected empty result.")
                        broadcast_message("error", {"message": "Failed to generate new round (empty result)."})
                else:
                    # Original round generation failed
                    broadcast_message("error", {"message": round_data["error"]})
            elif round_data:
                # Successfully generated round - broadcast to clients
                logging.info("[background_task] Round generation successful. Broadcasting...")
                broadcast_message("new_round", round_data)
                
                # Start preloading the next round immediately - only if not already preloading
                with preload_lock:
                    already_preloading = is_preloading
                    has_preloaded = preloaded_round is not None
                
                if not already_preloading and not has_preloaded:
                    logging.info("[background_task] Preloading next round...")
                    Thread(target=preload_next_round, daemon=True).start()
            else:
                logging.error("[background_task] Round generation returned unexpected empty result.")
                broadcast_message("error", {"message": "Failed to generate new round (empty result)."})
            
            # Reset the flag after processing
            logging.info("[background_task] Resetting new_round_requested flag to FALSE.")
            with lock:
                new_round_requested = False  # Reset flag AFTER processing
                
        else:
            # Idle time - preload rounds for better performance
            # If no round is preloaded and we're not processing a request, check if we should preload
            with preload_lock:
                no_preloaded_round = preloaded_round is None
                already_preloading = is_preloading
            
            if no_preloaded_round and not already_preloading:
                logging.info("[background_task] Idle, preloading a round...")
                Thread(target=preload_next_round, daemon=True).start()
            
        time.sleep(0.5)  # Check flags frequently for responsiveness

def preload_next_round():
    """
    Preload the next game round in the background for improved performance.
    
    This function generates a game round in advance, before it's requested,
    allowing for faster response times when users click "Next Round".
    The preloaded round is stored in memory until needed.
    
    Thread safety is maintained through locks to prevent race conditions
    with multiple threads accessing shared state.
    """
    global preloaded_round, is_preloading
    
    # Ensure only one preloading thread runs at a time using a lock
    with preload_lock:
        if is_preloading or preloaded_round is not None:
            logging.info("[preload_next_round] Already preloading or preloaded round exists. Skipping.")
            return
        is_preloading = True
    
    try:
        logging.info("[preload_next_round] Generating preloaded round...")
        next_round = generate_new_round()  # This logs its own duration
        
        # Only store successful round generations
        if isinstance(next_round, dict) and "error" in next_round:
            logging.error(f"[preload_next_round] Preloaded round generation failed: {next_round['error']}")
            # Don't store error rounds
        elif next_round:
            logging.info("[preload_next_round] Successfully generated preloaded round")
            with preload_lock:
                preloaded_round = next_round
        else:
            logging.error("[preload_next_round] Preloaded round generation returned unexpected empty result.")
    finally:
        # Always reset the preloading flag when done
        with preload_lock:
            is_preloading = False

# Start the background thread for continuous round generation and broadcasting
thread = Thread(target=background_task, daemon=True)
thread.start()

# --- API Endpoints ---

@app.route("/api/trigger_new_round", methods=["GET"])
def trigger_new_round():
    """
    API endpoint to trigger generation of a new game round.
    
    This endpoint sets a flag that signals the background thread
    to generate and broadcast a new round of statements to all
    connected clients. It prevents duplicate requests while a
    round is already being generated.
    
    Returns:
        JSON response indicating whether the request was accepted
        Status 200: New round triggered
        Status 202: Request acknowledged but round already in progress
    """
    global new_round_requested
    logging.info("[trigger_new_round] Endpoint hit.")
    
    # Enable CORS for this endpoint
    response = None
    
    if not new_round_requested:
        logging.info("[trigger_new_round] Setting new_round_requested flag to TRUE.")
        new_round_requested = True
        response = jsonify({"message": "New round generation triggered"})
        status_code = 200
    else:
        logging.warning("[trigger_new_round] Request received but generation already in progress/requested.")
        response = jsonify({"message": "New round generation already requested"})
        status_code = 202
        
    # Add CORS headers
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", "GET")
    
    return response, status_code

@app.route("/api/session", methods=["GET", "POST", "OPTIONS"])
def manage_session():
    """
    API endpoint to view or manage session history.
    
    GET:
    - Returns session statistics and optionally detailed history
    - Supports filtering for details, prompts, responses, and easter eggs
    
    POST:
    - Supports session management actions:
      - 'reset': Clear session history
      - 'new': Create a new session
      
    OPTIONS:
    - Handles CORS preflight requests
    
    Returns:
        GET: JSON response with session data
        POST: JSON response confirming the action taken
        OPTIONS: Empty response with CORS headers
    """
    # Handle OPTIONS request for CORS preflight
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        return response
        
    # Get current session ID
    session_id = get_session_id()
    
    if request.method == "GET":
        # Parse query parameters for filtering options
        detail = request.args.get("detail", "false").lower() == "true"           # Include full statement details
        include_prompts = request.args.get("prompts", "false").lower() == "true" # Include stored prompts
        include_responses = request.args.get("responses", "false").lower() == "true" # Include LLM responses
        easter_eggs_only = request.args.get("easter_eggs", "false").lower() == "true" # Filter to easter egg rounds
        
        # Get session history from Redis or fallback
        history = get_session_history(session_id)
        
        # Prepare base response with session metadata
        response_data = {
            "session_id": session_id,
            "round_count": history["round_count"],
            "rounds_in_history": len(history["rounds"]),
            "session_started_at": datetime.now().isoformat(),
            "using_redis": redis_client is not None
        }
        
        # Add rounds if detailed history is requested
        if detail:
            # If filtering for easter eggs only
            if easter_eggs_only and redis_client:
                # First identify which rounds are easter egg rounds
                easter_egg_rounds = set()
                try:
                    prompt_key = f"{REDIS_SESSION_PREFIX}{session_id}:prompts"
                    prompt_history = redis_client.lrange(prompt_key, 0, REDIS_MAX_HISTORY - 1)
                    
                    for prompt_json in prompt_history:
                        try:
                            prompt_data = json.loads(prompt_json)
                            if prompt_data.get("is_easter_egg_set", False):
                                easter_egg_rounds.add(prompt_data["round_number"])
                        except json.JSONDecodeError:
                            pass
                except Exception as e:
                    logging.error(f"Error getting easter egg round numbers: {e}")
                
                # Filter rounds to only include easter egg rounds
                filtered_rounds = []
                for i, round_data in enumerate(history["rounds"]):
                    # The index needs to be converted to a round number
                    round_num = history["round_count"] - i
                    if round_num in easter_egg_rounds:
                        filtered_rounds.append(round_data)
                
                response_data["rounds"] = filtered_rounds
            else:
                # Include all rounds
                response_data["rounds"] = history["rounds"]
            
        # Add prompts if requested and Redis is available
        if include_prompts and redis_client:
            try:
                prompt_key = f"{REDIS_SESSION_PREFIX}{session_id}:prompts"
                prompt_history = redis_client.lrange(prompt_key, 0, REDIS_MAX_HISTORY - 1)
                prompts = []
                
                for prompt_json in prompt_history:
                    try:
                        prompt_data = json.loads(prompt_json)
                        # If filtering for easter eggs, only include those prompts
                        if easter_eggs_only and not prompt_data.get("is_easter_egg_set", False):
                            continue
                        prompts.append(prompt_data)
                    except json.JSONDecodeError:
                        logging.error(f"Failed to decode prompt JSON: {prompt_json}")
                
                response_data["prompts"] = prompts
            except Exception as e:
                logging.error(f"Error retrieving prompts from Redis: {e}")
                response_data["prompts"] = []
                
        # Add responses if requested and Redis is available
        if include_responses and redis_client:
            try:
                response_key = f"{REDIS_SESSION_PREFIX}{session_id}:responses"
                response_history = redis_client.lrange(response_key, 0, REDIS_MAX_HISTORY - 1)
                responses = []
                
                # If filtering for easter eggs, we need the prompts to know which ones are easter egg rounds
                easter_egg_rounds = set()
                if easter_eggs_only:
                    try:
                        prompt_key = f"{REDIS_SESSION_PREFIX}{session_id}:prompts"
                        prompt_history = redis_client.lrange(prompt_key, 0, REDIS_MAX_HISTORY - 1)
                        
                        for prompt_json in prompt_history:
                            try:
                                prompt_data = json.loads(prompt_json)
                                if prompt_data.get("is_easter_egg_set", False):
                                    easter_egg_rounds.add(prompt_data["round_number"])
                            except json.JSONDecodeError:
                                pass
                    except Exception:
                        pass
                
                for response_json in response_history:
                    try:
                        response_data_item = json.loads(response_json)
                        # If filtering for easter eggs, only include responses from easter egg rounds
                        if easter_eggs_only and response_data_item["round_number"] not in easter_egg_rounds:
                            continue
                        responses.append(response_data_item)
                    except json.JSONDecodeError:
                        logging.error(f"Failed to decode response JSON: {response_json}")
                
                response_data["responses"] = responses
            except Exception as e:
                logging.error(f"Error retrieving responses from Redis: {e}")
                response_data["responses"] = []
        
        # Create response with CORS headers
        response = jsonify(response_data)
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        return response, 200
    
    elif request.method == "POST":
        # Handle different session management actions
        action = request.json.get("action", "")
        response_data = {}
        status_code = 200
        
        if action == "reset":
            # Reset session - clear all history
            if redis_client:
                try:
                    # Clear Redis keys for this session
                    session_key = f"{REDIS_SESSION_PREFIX}{session_id}"
                    statements_key = f"{REDIS_STATEMENT_PREFIX}{session_id}"
                    
                    # Get current round count for logging
                    round_count = int(redis_client.hget(session_key, "round_count") or "0")
                    
                    # Delete all session keys
                    redis_client.delete(session_key)
                    redis_client.delete(statements_key)
                    prompt_key = f"{REDIS_SESSION_PREFIX}{session_id}:prompts"
                    response_key = f"{REDIS_SESSION_PREFIX}{session_id}:responses"
                    redis_client.delete(prompt_key)
                    redis_client.delete(response_key)
                    
                    # Create a new session with reset count
                    redis_client.hset(session_key, "round_count", 0)
                    redis_client.expire(session_key, REDIS_SESSION_EXPIRY)
                    
                    logging.info(f"[manage_session] Redis session {session_id} reset. Cleared {round_count} rounds.")
                    response_data = {"message": f"Session reset. Cleared {round_count} rounds."}
                except Exception as e:
                    logging.error(f"[manage_session] Error resetting Redis session: {e}")
                    # Fall back to in-memory reset
            else:
                # In-memory fallback for reset
                with history_lock:
                    old_count = session_history["round_count"]
                    session_history = {
                        "rounds": [],
                        "round_count": 0
                    }
                    logging.info(f"[manage_session] In-memory session reset. Cleared {old_count} rounds.")
                    response_data = {"message": f"Session reset. Cleared {old_count} rounds."}
        
        elif action == "new":
            # Create a brand new session
            global current_session_id
            current_session_id = str(uuid.uuid4())
            logging.info(f"[manage_session] Created new session: {current_session_id}")
            response_data = {
                "message": "New session created",
                "session_id": current_session_id
            }
            
        else:
            # Invalid action requested
            response_data = {"error": "Invalid action. Use 'reset' to clear session history or 'new' to create a new session."}
            status_code = 400
            
        # Create response with CORS headers
        response = jsonify(response_data)
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        return response, status_code

@app.route("/api/game_stream")
def game_stream():
    """
    SSE endpoint that establishes a persistent connection to the client.
    
    This endpoint creates a Server-Sent Events (SSE) connection that:
    1. Registers the client to receive game updates
    2. Automatically triggers a new round when a client connects
    3. Streams events (new rounds, errors) to the client in real-time
    4. Maintains the connection with keep-alive messages
    5. Cleans up resources when the client disconnects
    
    Returns:
        A streaming response with SSE event data
    """
    global new_round_requested, preloaded_round
    
    # Log headers for debugging
    logging.info(f"[game_stream] Request headers: {request.headers}")
    
    # Create a message queue for this client
    queue = Queue()
    client_id = id(queue)
    with lock:
        message_queues[client_id] = queue
    logging.info(f"[game_stream] Client {client_id} connected.")
    
    # Automatically trigger a new round when a client connects
    # This provides immediate content rather than requiring client action
    if not new_round_requested:
        logging.info(f"[game_stream] Automatically triggering new round for client {client_id}.")
        new_round_requested = True

    def stream():
        """Generator function that yields SSE messages for this client."""
        logging.info(f"[game_stream] Starting stream generator for client {client_id}.")
        try:
            # Send an initial message to ensure the connection is established
            yield "data: {\"type\":\"connected\",\"message\":\"Connection established\"}\n\n"
            logging.info(f"[game_stream] Sent initial connection message to client {client_id}")
            
            while True:
                try:
                    # Wait for messages from the queue with a timeout
                    # This allows for periodic keep-alive messages
                    msg = queue.get(timeout=20)  # Shorter timeout for more frequent keep-alives
                    logging.info(f"[game_stream] Client {client_id} received message from queue. Yielding.")
                    yield msg
                except Empty:
                    # If queue is empty after timeout, send keep-alive to maintain connection
                    yield ": keep-alive\n\n"
                    logging.info(f"[game_stream] Sent keep-alive to client {client_id}")
        except GeneratorExit:
            # Client disconnected
            logging.info(f"[game_stream] Client {client_id} disconnected (GeneratorExit).")
        finally:
            # Always clean up client resources when connection ends
            logging.info(f"[game_stream] Cleaning up queue for client {client_id}.")
            with lock:
                if client_id in message_queues:
                    del message_queues[client_id]
                    logging.info(f"[game_stream] Removed queue for client {client_id}.")

    # Enable CORS for SSE endpoint
    response = Response(stream(), mimetype="text/event-stream")
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", "GET")
    response.headers.add("Cache-Control", "no-cache")
    response.headers.add("Connection", "keep-alive")
    response.headers.add("X-Accel-Buffering", "no")  # Disable proxy buffering
    return response

# --- Static File Serving ---
@app.route("/")
@app.route("/<path:path>")
def serve(path=""):
    """
    Handle all web requests for static files and the main application.
    
    This function serves the frontend application files:
    - For the root URL (/), serves index.html
    - For specific file paths, serves the requested static file
    - Includes security checks to prevent directory traversal
    - Falls back to index.html for client-side routing (SPA support)
    
    Args:
        path (str): The path requested by the client, relative to static folder
        
    Returns:
        The requested file content or error message if file not found
    """
    # Get the configured static folder path
    static_folder_path = app.static_folder
    if static_folder_path is None:
        logging.error("[serve] Static folder not configured.")
        return "Static folder not configured", 404

    # Security: Prevent directory traversal attacks by normalizing path
    # and checking that it stays within the static folder
    safe_path = os.path.normpath(os.path.join(static_folder_path, path))
    if not safe_path.startswith(os.path.abspath(static_folder_path)):
        logging.warning(f"[serve] Attempted directory traversal: {path}")
        return "Invalid path", 404

    # If path is a specific file that exists, serve it directly
    if path != "" and os.path.exists(safe_path) and os.path.isfile(safe_path):
        return send_from_directory(static_folder_path, path)
    else:
        # Otherwise serve index.html (for SPA routing)
        index_path = os.path.join(static_folder_path, "index.html")
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, "index.html")
        else:
            logging.error("[serve] index.html not found in static folder.")
            return "index.html not found", 404

# --- Main Application Entry Point ---
if __name__ == "__main__":
    # Start the Flask development server when script is run directly
    # Get port from environment variable or use default
    port = int(os.getenv('PORT', 3002))  # Default to 3002 for local development (avoids conflicts)
    logging.info(f"Starting Flask development server for local testing on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)