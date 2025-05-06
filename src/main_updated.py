# src/main.py
import os
import sys
import json
import time
import logging
import yaml  # Import YAML library
from threading import Lock, Thread
from queue import Queue, Empty
from datetime import datetime # For timestamps

from flask import Flask, Response, jsonify, send_from_directory
import anthropic

# Ensure the src directory is in the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# --- Configuration & Initialization ---
# Configure logging with timestamps
logging.basicConfig(level=logging.INFO, format="%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logging.info("Logging configured with timestamp format.")

app = Flask(__name__, static_folder="static")

# Load Anthropic API Key
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
if not anthropic_api_key:
    logging.warning("ANTHROPIC_API_KEY environment variable not set. API calls will fail.")
    anthropic_api_key = "placeholder_key"
else:
    logging.info("ANTHROPIC_API_KEY loaded from environment.")

# Load Claude Prompt from YAML
claude_prompt = ""
try:
    logging.info("Attempting to load config.yaml from /app/config.yaml")
    with open("/app/config.yaml", "r") as f:
        config_data = yaml.safe_load(f)
        claude_prompt = config_data.get("claude_prompt")
        if not claude_prompt:
            logging.error("claude_prompt not found or empty in config.yaml")
        else:
            logging.info("Claude prompt loaded successfully from config.yaml")
except FileNotFoundError:
    logging.error("/app/config.yaml not found.")
except yaml.YAMLError as e:
    logging.error(f"Error parsing config.yaml: {e}")
except Exception as e:
    logging.error(f"An unexpected error occurred loading config.yaml: {e}")

# Initialize Anthropic Client
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

# --- SSE Setup ---
message_queues = {}
lock = Lock()
new_round_requested = True  # Set to True initially so game starts immediately

def generate_new_round():
    """Generates a new round using the Anthropic API."""
    global new_round_requested
    start_time = time.time()
    logging.info("[generate_new_round] START")
    if not anthropic_client:
        logging.error("[generate_new_round] Anthropic client not initialized.")
        return {"error": "Anthropic client not initialized. Check API key."}
    if not claude_prompt:
        logging.error("[generate_new_round] Claude prompt is not loaded.")
        return {"error": "Claude prompt not loaded. Check config.yaml."}

    try:
        prompt_to_send = claude_prompt
        logging.info("[generate_new_round] Sending request to Anthropic API...")
        api_start_time = time.time()
        message = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1000,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt_to_send}]
        )
        api_end_time = time.time()
        logging.info(f"[generate_new_round] Received response from Anthropic API. Duration: {api_end_time - api_start_time:.3f}s")
        response_text = message.content[0].text
        try:
            parse_start_time = time.time()
            round_data = json.loads(response_text)
            parse_end_time = time.time()
            logging.info(f"[generate_new_round] Successfully parsed round data. Duration: {parse_end_time - parse_start_time:.3f}s")
            return round_data
        except json.JSONDecodeError as e:
            logging.error(f"[generate_new_round] Failed to parse JSON: {e}")
            logging.error(f"[generate_new_round] Raw response text: {response_text}")
            return {"error": f"Failed to parse response from LLM: {e}"}

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
    """Wraps data and sends it to all connected SSE clients."""
    logging.info(f"[broadcast_message] Preparing to broadcast event type 	\"{event_type}\"")
    message_data = {"type": event_type}
    if event_type == "error":
        message_data["message"] = payload.get("message", "Unknown error")
    else:
        message_data["payload"] = payload

    with lock:
        logging.info(f"[broadcast_message] Acquiring lock. Broadcasting to {len(message_queues)} clients.")
        for client_id, queue in message_queues.items():
            try:
                json_data = json.dumps(message_data)
                msg = f"data: {json_data}\n\n"
                logging.info(f"[broadcast_message] Putting message for client {client_id} into queue.")
                queue.put(msg)
            except TypeError as e:
                logging.error(f"[broadcast_message] Failed to serialize data for client {client_id}, event 	\"{event_type}\": {e}")
                logging.error(f"[broadcast_message] Data causing error: {message_data}")
        logging.info("[broadcast_message] Releasing lock.")
    logging.info(f"[broadcast_message] Finished broadcasting event type 	\"{event_type}\"")

def background_task():
    """Background thread to generate and broadcast new rounds when requested."""
    global new_round_requested
    logging.info("[background_task] Starting background thread.")
    # Log that the game is starting immediately
    logging.info("[background_task] Initial round generation enabled - game will start immediately")
    
    while True:
        if new_round_requested:
            logging.info("[background_task] Flag new_round_requested is TRUE. Processing...")
            round_data = generate_new_round() # This logs its own duration
            if isinstance(round_data, dict) and "error" in round_data:
                logging.error(f"[background_task] Round generation failed: {round_data['error']}")
                broadcast_message("error", {"message": round_data["error"]})
            elif round_data:
                logging.info("[background_task] Round generation successful. Broadcasting...")
                broadcast_message("new_round", round_data)
            else:
                logging.error("[background_task] Round generation returned unexpected empty result.")
                broadcast_message("error", {"message": "Failed to generate new round (empty result)."})
            
            logging.info("[background_task] Resetting new_round_requested flag to FALSE.")
            new_round_requested = False # Reset flag AFTER processing
        else:
            # Optional: Log when idle to show thread is alive
            # logging.debug("[background_task] Idle, flag is FALSE.") 
            pass
        time.sleep(0.5) # Check flag more frequently

# Start the background thread
thread = Thread(target=background_task, daemon=True)
thread.start()
logging.info("Background thread started - game will start immediately upon client connection")

# --- API Endpoints ---

@app.route("/api/trigger_new_round", methods=["GET"])
def trigger_new_round():
    global new_round_requested
    logging.info("[trigger_new_round] Endpoint hit.")
    if not new_round_requested:
        logging.info("[trigger_new_round] Setting new_round_requested flag to TRUE.")
        new_round_requested = True
        return jsonify({"message": "New round generation triggered"}), 200
    else:
        logging.warning("[trigger_new_round] Request received but generation already in progress/requested.")
        return jsonify({"message": "New round generation already requested"}), 202

@app.route("/api/game_stream")
def game_stream():
    queue = Queue()
    client_id = id(queue)
    with lock:
        message_queues[client_id] = queue
    logging.info(f"[game_stream] Client {client_id} connected.")

    def stream():
        logging.info(f"[game_stream] Starting stream generator for client {client_id}.")
        try:
            while True:
                try:
                    # logging.debug(f"[game_stream] Client {client_id} waiting for message...")
                    msg = queue.get(timeout=120) # Increased timeout
                    logging.info(f"[game_stream] Client {client_id} received message from queue. Yielding.")
                    yield msg
                except Empty:
                    # logging.debug(f"[game_stream] Client {client_id} queue empty, sending keep-alive.")
                    yield ": keep-alive\n\n"
        except GeneratorExit:
            logging.info(f"[game_stream] Client {client_id} disconnected (GeneratorExit).")
        finally:
            logging.info(f"[game_stream] Cleaning up queue for client {client_id}.")
            with lock:
                if client_id in message_queues:
                    del message_queues[client_id]
                    logging.info(f"[game_stream] Removed queue for client {client_id}.")

    return Response(stream(), mimetype="text/event-stream")

# --- Static File Serving ---
@app.route("/")
@app.route("/<path:path>")
def serve(path=""):
    # logging.debug(f"[serve] Request for path: 	\"{path if path else '/'}\"")
    static_folder_path = app.static_folder
    if static_folder_path is None:
        logging.error("[serve] Static folder not configured.")
        return "Static folder not configured", 404

    safe_path = os.path.normpath(os.path.join(static_folder_path, path))
    if not safe_path.startswith(os.path.abspath(static_folder_path)):
        logging.warning(f"[serve] Attempted directory traversal: {path}")
        return "Invalid path", 404

    if path != "" and os.path.exists(safe_path) and os.path.isfile(safe_path):
        # logging.debug(f"[serve] Serving static file: {path}")
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, "index.html")
        if os.path.exists(index_path):
            # logging.debug(f"[serve] Serving index.html for path: {path if path else '/'}")
            return send_from_directory(static_folder_path, "index.html")
        else:
            logging.error("[serve] index.html not found in static folder.")
            return "index.html not found", 404

if __name__ == "__main__":
    logging.info("Starting Flask development server for local testing on 0.0.0.0:3001")
    app.run(host="0.0.0.0", port=3001, debug=False)