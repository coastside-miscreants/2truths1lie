// Setup file for Jest tests

// Mock global browser functions that aren't available in jsdom
global.requestAnimationFrame = callback => setTimeout(callback, 0);

// Mock window.location
Object.defineProperty(window, 'location', {
  value: {
    hostname: 'localhost',
  },
  writable: true,
});

// Define global functions from script.js that we'll test directly
global.showLoadingIndicator = function() {
  const statementsContainer = document.getElementById('statements-container');
  statementsContainer.innerHTML = `
    <div class="loading-content">
      <div class="spinner"></div>
      <p>The gerbils in F*ckchops mind are thinking hard...</p>
    </div>
  `;
};

global.hideLoadingIndicator = function() {
  // No-op in our implementation
};

global.gameInProgress = true;
global.currentStatements = [];
global.correctScore = 0;
global.incorrectScore = 0;
global.roundsPlayed = 0;

global.handleNewRoundData = function(data) {
  global.currentStatements = data.statements;
  global.displayStatements();
};

global.handleServerError = function(errorMessage) {
  const statementsContainer = document.getElementById('statements-container');
  statementsContainer.innerHTML = `
    <div class="statement-placeholder error">Oops! Couldn't load the next round. Server error: ${errorMessage}</div>
  `;
  global.gameInProgress = false;
};

global.displayStatements = function() {
  const statementsContainer = document.getElementById('statements-container');
  statementsContainer.innerHTML = "";
  
  // Store the shuffled order to use it later for explanations
  window.displayedStatementOrder = [...global.currentStatements];
  
  window.displayedStatementOrder.forEach((statement) => {
    const buttonContainer = document.createElement("div");
    buttonContainer.classList.add("statement-container");
    buttonContainer.style.position = "relative";
    
    const button = document.createElement("button");
    button.classList.add("statement-button");
    button.textContent = statement.text;
    button.dataset.statementText = statement.text;
    button.addEventListener("click", global.handleStatementClick);
    
    const overlay = document.createElement("div");
    overlay.classList.add("statement-overlay");
    // Style properties set inline
    
    buttonContainer.appendChild(button);
    buttonContainer.appendChild(overlay);
    statementsContainer.appendChild(buttonContainer);
  });
};

global.triggerFlashFeedback = function(isCorrect) {
  const flashFeedback = document.getElementById('flash-feedback');
  const message = isCorrect ? "You are smart AF!" : "You are dumb AF!";
  
  flashFeedback.textContent = message;
  flashFeedback.className = "hidden";
  
  setTimeout(() => {
    flashFeedback.classList.remove("hidden");
  }, 0);
  
  setTimeout(() => {
    flashFeedback.classList.add("hidden");
  }, 3000);
};

global.showStatementFeedback = function(button, isCorrect) {
  const container = button.parentElement;
  const overlay = container.querySelector(".statement-overlay");
  
  overlay.textContent = isCorrect ? "CORRECT!" : "WRONG!";
  overlay.className = "statement-overlay " + (isCorrect ? "correct" : "incorrect");
  
  if (isCorrect) {
    overlay.style.backgroundColor = "rgba(40, 167, 69, 0.85)";
  } else {
    overlay.style.backgroundColor = "rgba(249, 87, 56, 0.85)";
  }
  
  overlay.style.opacity = "1";
};

global.handleStatementClick = function(event) {
  if (!global.gameInProgress) {
    return;
  }
  
  global.gameInProgress = false;
  global.roundsPlayed++;
  
  const selectedButton = event.target;
  const selectedText = selectedButton.dataset.statementText;
  const selectedStatement = global.currentStatements.find(s => s.text === selectedText);
  
  if (!selectedStatement) {
    return;
  }
  
  document.querySelectorAll(".statement-button").forEach(btn => {
    btn.disabled = true;
    btn.style.cursor = "default";
    if (btn === selectedButton) {
      btn.style.borderWidth = "4px";
    }
  });
  
  const feedbackText = document.getElementById('feedback-text');
  let wasCorrect = false;
  
  if (selectedStatement.isLie) {
    feedbackText.textContent = "Correct! You found the lie!";
    feedbackText.className = "correct";
    global.correctScore++;
    wasCorrect = true;
  } else {
    feedbackText.textContent = "Incorrect! That was actually true.";
    feedbackText.className = "incorrect";
    global.incorrectScore++;
    wasCorrect = false;
  }
  
  global.showStatementFeedback(selectedButton, wasCorrect);
  
  document.querySelectorAll(".statement-button").forEach(btn => {
    if (btn !== selectedButton) {
      const btnText = btn.dataset.statementText;
      const statement = global.currentStatements.find(s => s.text === btnText);
      if (statement && statement.isLie) {
        global.showStatementFeedback(btn, true);
      }
    }
  });
  
  global.triggerFlashFeedback(wasCorrect);
  global.displayExplanations();
  global.updateScoreboard();
  
  const feedbackArea = document.getElementById('feedback-area');
  const nextRoundButton = document.getElementById('next-round-button');
  
  feedbackArea.classList.remove("hidden");
  nextRoundButton.classList.remove("hidden");
};

global.displayExplanations = function() {
  const explanationsContainer = document.getElementById('explanations');
  explanationsContainer.innerHTML = "";
  
  window.displayedStatementOrder.forEach(statement => {
    const p = document.createElement("p");
    const explanationClass = statement.isLie ? "false-explanation" : "true-explanation";
    const type = statement.isLie ? "Lie" : "Truth";
    p.classList.add(explanationClass);
    p.innerHTML = `<strong>${type}:</strong> ${statement.text}<br><em>${statement.explanation}</em>`;
    explanationsContainer.appendChild(p);
  });
};

global.updateScoreboard = function() {
  const correctScoreSpan = document.getElementById('correct-score');
  const incorrectScoreSpan = document.getElementById('incorrect-score');
  const roundsPlayedSpan = document.getElementById('rounds-played');
  
  correctScoreSpan.textContent = global.correctScore;
  incorrectScoreSpan.textContent = global.incorrectScore;
  roundsPlayedSpan.textContent = global.roundsPlayed;
};

global.requestNewRound = function() {
  const feedbackArea = document.getElementById('feedback-area');
  const nextRoundButton = document.getElementById('next-round-button');
  const flashFeedback = document.getElementById('flash-feedback');
  
  feedbackArea.classList.add("hidden");
  nextRoundButton.classList.add("hidden");
  flashFeedback.classList.add("hidden");
  global.gameInProgress = true;
  
  global.showLoadingIndicator();
  
  fetch('/api/trigger_new_round')
    .then(response => {
      if (!response.ok) {
        const statementsContainer = document.getElementById('statements-container');
        statementsContainer.innerHTML = `
          <div class="statement-placeholder error">Failed to trigger new round generation. Please try again.</div>
        `;
      }
    })
    .catch(error => {
      const statementsContainer = document.getElementById('statements-container');
      statementsContainer.innerHTML = `
        <div class="statement-placeholder error">Error connecting to server: ${error.message}</div>
      `;
    });
};