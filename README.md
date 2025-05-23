# 2 Truths & AI Game

This project implements a web-based version of the "2 Truths and a Lie" game (specifically, 2 truths and 1 AI-generated lie), powered by Anthropic's Claude LLM.

<img width="792" alt="Screenshot 2025-05-06 at 12 29 33 AM" src="https://github.com/user-attachments/assets/811b9ace-5fbb-40ed-ba0b-0ac334830693" />

## Features

*   Fetches game rounds (2 truths, 1 lie) from Anthropic Claude 3.5 Sonnet.
*   Uses Server-Sent Events (SSE) for dynamic updates.
*   Playful UI inspired by "Meow Mart" and 1960s Batman "POW!" effects.
*   Session-based scoring (Correct / Incorrect / Rounds Played).
*   Extensive console logging on both frontend and backend for debugging.
*   Ready for deployment using Docker Compose.
*   Redis integration for persistent session history.
*   Automatic preloading of next rounds for faster gameplay.
*   Easter egg content on every third round.

## How the Game Works

1. The game presents three statements to the player.
2. Two statements are true facts, while one is a false statement generated by Claude AI.
3. The player must identify which statement is the lie.
4. After selecting a statement, the game reveals the correct answer and provides explanations for all three statements.
5. The player's score is tracked throughout their session.
6. Content is automatically diverse across different knowledge domains.

## Technology Stack

- **Backend**: Python with Flask for the web server
- **AI**: Anthropic's Claude 3.5 Sonnet for statement generation
- **Frontend**: HTML, CSS, and JavaScript
- **Data Persistence**: Redis (optional, falls back to in-memory storage)
- **Communications**: Server-Sent Events (SSE) for real-time updates
- **Deployment**: Docker and Docker Compose

## Project Structure

```
/two_truths_ai_game
|-- Dockerfile             # Defines the Docker image for the Flask app
|-- docker-compose.yml     # Defines the Docker service
|-- requirements.txt       # Python dependencies
|-- test-requirements.txt  # Python testing dependencies
|-- package.json           # Node.js dependencies for frontend testing
|-- jest.config.js         # Jest configuration for frontend tests
|-- pytest.ini             # Pytest configuration
|-- .babelrc               # Babel configuration for Jest
|-- config.yaml            # Contains the Claude LLM prompt
|-- run_tests.sh           # Convenient script to run all tests
|-- src/
|   |-- static/
|   |   |-- index.html     # Main HTML file
|   |   |-- style.css      # CSS styles
|   |   |-- script.js      # Frontend JavaScript logic
|   |-- main.py            # Flask backend (API, SSE, static serving)
|   |-- models/            # Database models
|   |-- routes/            # API route definitions
|-- tests/
|   |-- test_backend.py    # Backend unit tests
|   |-- test_frontend.js   # Frontend unit tests
|   |-- test_integration.py # Integration tests
|   |-- setup.js           # Frontend test setup
|   |-- mocks/             # Mock files for testing
|-- venv/                  # Virtual environment (not included in deployment)
|-- .env                   # Optional: For local environment variables (NOT committed)
|-- README.md              # This file
```

## Technical Details

### Backend Architecture

The backend is built with Flask and provides several key functionalities:

1. **LLM Integration**: Makes API calls to Anthropic's Claude LLM to generate game rounds.
2. **Server-Sent Events**: Provides a streaming API endpoint for real-time game updates.
3. **Session Management**: Maintains player sessions with Redis or in-memory fallback.
4. **Background Processing**: Preloads new rounds in the background for improved performance.
5. **Error Handling**: Comprehensive error handling for API calls and client connections.

### Frontend Architecture

The frontend is built with vanilla JavaScript and implements:

1. **SSE Connection**: Establishes and maintains a connection to the server's event stream.
2. **Game State Management**: Tracks current statements, score, and game state.
3. **Dynamic UI Updates**: Renders game elements and feedback based on player actions.
4. **Animations**: Provides visual feedback with animations and color coding.

### Redis Integration

The application uses Redis for persistent session history:

1. **Session Storage**: Stores player sessions, game rounds, and API interactions.
2. **Fallback Mechanism**: Falls back to in-memory storage if Redis is unavailable.
3. **Key Expiration**: Implements automatic cleanup of old session data.

## Setup and Running

1.  **Prerequisites:**
    *   Docker
    *   Docker Compose
    *   An Anthropic API Key

2.  **Configure API Key:**
    *   Create a file named `.env` in the root directory.
    *   Add your Anthropic API key to this file like so:
        ```
        ANTHROPIC_API_KEY=your_actual_api_key_here
        ```
    *   Replace `your_actual_api_key_here` with your real key.
    *   **Important:** Do not commit the `.env` file to version control.

3.  **Configure Redis (Optional):**
    *   Redis configuration can be added to the `.env` file:
        ```
        REDIS_HOST=your_redis_host
        REDIS_PORT=your_redis_port
        ```
    *   If not configured, the application will fall back to in-memory storage.

4.  **Configure Port (Optional):**
    *   You can customize the port the application runs on:
        ```
        PORT=8080
        ```
    *   If not configured, the default port 3001 will be used.

5.  **Build and Run with Docker Compose:**
    *   Open a terminal in the project's root directory.
    *   Run the command:
        ```bash
        docker-compose up --build
        ```
    *   This command will build the Docker image (if it doesn't exist) and start the web service.

6.  **Access the Game:**
    *   Open your web browser and navigate to `http://localhost:PORT` where PORT is the port you configured (default: 3001).

7.  **Stopping the Game:**
    *   Press `Ctrl+C` in the terminal where `docker-compose up` is running.
    *   You can optionally run `docker-compose down` to remove the container.

## Local Development

For local development without Docker:

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set environment variables:
   ```bash
   export ANTHROPIC_API_KEY=your_api_key  # On Windows: set ANTHROPIC_API_KEY=your_api_key
   ```

4. Configure port (optional):
   ```bash
   export PORT=8080  # On Windows: set PORT=8080
   ```

5. Run the Flask application:
   ```bash
   python src/main.py
   ```

6. Access the application at the configured port (default: `http://localhost:3002`)

## Advanced Configuration

### Claude LLM Prompt

The game uses a configurable prompt defined in `config.yaml`. The prompt instructs Claude to:

1. Generate two surprising but true facts and one believable lie.
2. Make the lie subtle and hard to identify without specific knowledge.
3. Use diverse topics across different knowledge domains.
4. Provide explanations for why each statement is true or false.
5. Include easter egg content about specific characters on every third round.

You can modify the prompt in `config.yaml` to change the game's behavior and content style.

### Session Management

The application implements session management with these features:

1. **Session Persistence**: Game history is stored across server restarts when Redis is enabled.
2. **Session Reset**: Players can reset their session history via the API.
3. **Cross-Topic Memory**: The system tracks previous topics to avoid repetition.

## API Endpoints

The application provides several API endpoints:

- **GET /api/game_stream**: SSE endpoint for receiving game updates.
- **GET /api/trigger_new_round**: Triggers generation of a new game round.
- **GET /api/session**: Returns current session statistics and history.
- **POST /api/session**: Handles session management actions (reset, new).

## Testing

The project includes comprehensive testing for both frontend and backend components.

### Prerequisites for Testing

- Docker (for running tests in a consistent environment)
- Python 3.8+ (for local testing)
- Node.js 14+ (for local frontend tests)
- Chrome browser (for local integration tests)

### Test Structure

- **Backend Tests**: Python tests using pytest
- **Frontend Tests**: JavaScript tests using Jest and jsdom
- **Integration Tests**: End-to-end tests using Selenium WebDriver

### Running Tests

#### Running tests with Docker (Recommended)

The easiest way to run tests is using Docker, which provides a consistent environment:

```bash
./test_in_docker.sh
```

This script will:
- Build a test Docker image using Dockerfile.test
- Run all the unit tests inside the container
- Generate a coverage report

#### Running tests locally

**Backend Tests:**

```bash
# Install test dependencies
pip install -r test-requirements.txt

# Run backend tests
pytest tests/test_backend.py -v
```

**Frontend Tests:**

```bash
# Install Node.js dependencies
npm install

# Run frontend tests
npm run test:frontend
```

**Integration Tests:**

```bash
# Install test dependencies
pip install -r test-requirements.txt

# Run integration tests
pytest tests/test_integration.py -v
```

### Test Coverage

The tests cover:

- **Backend**:
  - API endpoints
  - Game logic functions
  - Error handling
  - Session management
  - Redis integration

- **Frontend**:
  - UI rendering
  - Game state management
  - User interactions
  - SSE connection handling
  - Error states

## Development Notes

*   The Flask backend uses `gunicorn` in the Docker container for a more production-ready setup.
*   SSE is used for pushing new rounds from the server to the client.
*   Frontend requests `/api/trigger_new_round` to signal the backend to generate and push a new round via the `/api/game_stream` SSE endpoint.
*   Extensive logging is available in the browser's developer console and the Docker container logs (`docker-compose logs -f web`).
*   Test-driven development is encouraged - run tests frequently when making changes.

## License

This project is for educational and demonstration purposes only.

## Credits

- Built with Anthropic's Claude API
- UI design inspired by classic comic book aesthetics and playful digital interfaces
