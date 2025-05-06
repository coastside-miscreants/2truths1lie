document.addEventListener("DOMContentLoaded", () => {
    console.log("DOM fully loaded and parsed");

    // --- DOM Elements ---
    const statementsContainer = document.getElementById("statements-container");
    const feedbackArea = document.getElementById("feedback-area");
    const feedbackText = document.getElementById("feedback-text");
    const explanationsContainer = document.getElementById("explanations");
    const nextRoundButton = document.getElementById("next-round-button");
    const correctScoreSpan = document.getElementById("correct-score");
    const incorrectScoreSpan = document.getElementById("incorrect-score");
    const roundsPlayedSpan = document.getElementById("rounds-played");
    const flashFeedback = document.getElementById("flash-feedback"); // Get the flash element

    console.log("DOM elements retrieved");

    // --- Game State ---
    let currentStatements = [];
    let correctScore = 0;
    let incorrectScore = 0;
    let roundsPlayed = 0;
    let gameInProgress = false; // To prevent multiple clicks during feedback
    let eventSource = null; // For SSE connection

    console.log("Initial game state set");

    // --- Core Functions ---
    function connectSSE() {
        console.log("Attempting to connect to SSE endpoint...");
        if (eventSource) {
            console.log("Closing existing SSE connection.");
            eventSource.close();
        }
        eventSource = new EventSource("/api/game_stream");

        eventSource.onopen = function() {
            console.log("SSE connection opened successfully.");
            // Game now starts automatically on the server when client connects
            // Prepare UI for incoming round
            statementsContainer.innerHTML = 
                `<div class="statement-placeholder">Generating new round... hang tight!</div>`;
            feedbackArea.classList.add("hidden");
            nextRoundButton.classList.add("hidden");
            flashFeedback.classList.add("hidden");
            flashFeedback.classList.remove("flashing", "flash-correct", "flash-incorrect");
            gameInProgress = true;
            console.log("Waiting for server to automatically generate first round...");
        };

        eventSource.onmessage = function(event) {
            console.log("SSE message received:", event.data);
            try {
                const data = JSON.parse(event.data);
                if (data.type === "new_round") {
                    handleNewRoundData(data.payload);
                } else if (data.type === "error") {
                    handleServerError(data.message);
                } else {
                    console.warn("Received unknown SSE message type:", data.type);
                }
            } catch (error) {
                console.error("Error parsing SSE message:", error, "Raw data:", event.data);
                handleServerError("Received invalid data from server.");
            }
        };

        eventSource.onerror = function(error) {
            console.error("SSE connection error:", error);
            statementsContainer.innerHTML = 
                `<div class="statement-placeholder error">Connection to game server lost. Please refresh the page to try again.</div>`;
            if (eventSource) eventSource.close();
        };
    }

    function requestNewRound() {
        console.log("Requesting new round from server...");
        statementsContainer.innerHTML = 
            `<div class="statement-placeholder">Generating new round... hang tight!</div>`;
        feedbackArea.classList.add("hidden");
        nextRoundButton.classList.add("hidden");
        flashFeedback.classList.add("hidden"); // Ensure flash is hidden on new round
        flashFeedback.classList.remove("flashing", "flash-correct", "flash-incorrect"); // Clean up classes
        gameInProgress = true;

        fetch("/api/trigger_new_round")
            .then(response => {
                if (!response.ok) {
                    console.error("Failed to trigger new round generation on server.");
                }
            })
            .catch(error => {
                console.error("Error triggering new round:", error);
            });
    }

    function handleNewRoundData(data) {
        console.log("Processing new round data:", data);
        if (!data.statements || data.statements.length !== 3) {
            console.error("Invalid new round data format received:", data);
            handleServerError("Received invalid round data from server.");
            return;
        }
        currentStatements = data.statements;
        displayStatements();
    }

    function handleServerError(errorMessage) {
        console.error("Server error reported:", errorMessage);
        statementsContainer.innerHTML = 
            `<div class="statement-placeholder error">Oops! Couldn't load the next round. Server error: ${errorMessage}</div>`;
        gameInProgress = false;
    }

    function displayStatements() {
        console.log("Displaying statements:", currentStatements);
        statementsContainer.innerHTML = "";
        const shuffledStatements = [...currentStatements].sort(() => Math.random() - 0.5);
        console.log("Shuffled statements for display:", shuffledStatements);

        shuffledStatements.forEach((statement) => {
            const button = document.createElement("button");
            button.classList.add("statement-button");
            button.textContent = statement.text;
            button.dataset.statementText = statement.text;
            button.addEventListener("click", handleStatementClick);
            statementsContainer.appendChild(button);
        });
        console.log("Statement buttons added to DOM.");
    }

    // --- Function to trigger flashing feedback ---
    function triggerFlashFeedback(isCorrect) {
        const message = isCorrect ? "You are smart AF!" : "You are dumb AF!";
        const cssClass = isCorrect ? "flash-correct" : "flash-incorrect";
        console.log(`Triggering flash feedback: ${message}`);

        flashFeedback.textContent = message;
        // Reset classes before adding new ones
        flashFeedback.className = "hidden"; // Start hidden
        // Use requestAnimationFrame to ensure classes are applied after reset
        requestAnimationFrame(() => {
            flashFeedback.classList.remove("hidden");
            flashFeedback.classList.add(cssClass, "flashing");
        });

        // Remove the flashing class after animation completes (3 flashes * 0.4s = 1.2s)
        // Add a small buffer
        setTimeout(() => {
            flashFeedback.classList.remove("flashing");
            flashFeedback.classList.add("hidden"); // Hide it again
            console.log("Flash feedback animation complete.");
        }, 1300); // 1.3 seconds
    }

    function handleStatementClick(event) {
        console.log("Statement button clicked:", event.target.textContent);
        if (!gameInProgress) {
            console.warn("Statement clicked but game is not in progress. Ignoring.");
            return;
        }

        gameInProgress = false;
        roundsPlayed++;
        console.log(`Round ${roundsPlayed} ended.`);

        const selectedButton = event.target;
        const selectedText = selectedButton.dataset.statementText;
        const selectedStatement = currentStatements.find(s => s.text === selectedText);

        if (!selectedStatement) {
            console.error("Could not find selected statement data for text:", selectedText);
            return;
        }
        console.log("Selected statement object:", selectedStatement);

        document.querySelectorAll(".statement-button").forEach(btn => {
            btn.disabled = true;
            btn.style.cursor = "default";
            if (btn === selectedButton) {
                btn.style.borderWidth = "4px";
                console.log("Highlighting selected button.");
            }
        });
        console.log("All statement buttons disabled.");

        let wasCorrect = false;
        if (selectedStatement.isLie) {
            console.log("Correct guess!");
            feedbackText.textContent = "Correct! You found the lie!";
            feedbackText.className = "correct";
            correctScore++;
            wasCorrect = true;
        } else {
            console.log("Incorrect guess.");
            feedbackText.textContent = "Incorrect! That was actually true.";
            feedbackText.className = "incorrect";
            incorrectScore++;
            wasCorrect = false;
        }

        // Trigger the flashing feedback
        triggerFlashFeedback(wasCorrect);

        displayExplanations();
        updateScoreboard();

        feedbackArea.classList.remove("hidden");
        nextRoundButton.classList.remove("hidden");
        console.log("Feedback and next round button displayed.");
    }

    function displayExplanations() {
        console.log("Displaying explanations.");
        explanationsContainer.innerHTML = "";
        currentStatements.forEach(statement => {
            const p = document.createElement("p");
            const explanationClass = statement.isLie ? "false-explanation" : "true-explanation";
            const type = statement.isLie ? "Lie" : "Truth";
            p.classList.add(explanationClass);
            p.innerHTML = `<strong>${type}:</strong> ${statement.text}<br><em>${statement.explanation}</em>`;
            explanationsContainer.appendChild(p);
        });
    }

    function updateScoreboard() {
        console.log(`Updating scoreboard: Correct=${correctScore}, Incorrect=${incorrectScore}, Rounds=${roundsPlayed}`);
        correctScoreSpan.textContent = correctScore;
        incorrectScoreSpan.textContent = incorrectScore;
        roundsPlayedSpan.textContent = roundsPlayed;
    }

    // --- Event Listeners ---
    nextRoundButton.addEventListener("click", () => {
        console.log("Next Round button clicked.");
        requestNewRound();
    });

    // --- Initial Load ---
    console.log("Initiating SSE connection...");
    connectSSE(); 
});