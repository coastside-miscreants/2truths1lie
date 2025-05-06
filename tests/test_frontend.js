/**
 * Frontend JavaScript Test Suite for Two Truths & AI Game
 * 
 * This file contains unit tests for the frontend JavaScript code.
 * The tests use Jest with jsdom for DOM simulation.
 */

// Mock the DOM environment
document.body.innerHTML = `
<div class="container">
  <header>
    <div class="title-container">
      <h1 class="game-title">2 Truths & AI</h1>
      <div id="flash-feedback" class="hidden"></div>
    </div>
    <div class="score-board">
      <span>Score: </span>
      <span id="correct-score">0</span> Correct / 
      <span id="incorrect-score">0</span> Incorrect (
      <span id="rounds-played">0</span> Rounds)
    </div>
  </header>
  <main id="game-area">
    <p class="instructions">Which one is the lie?</p>
    <div id="statements-container">
      <!-- Statements will be loaded here by JavaScript -->
      <div class="statement-placeholder">Loading statements...</div> 
    </div>
    <div id="feedback-area" class="hidden">
      <button id="next-round-button" class="hidden">Next Round</button>
      <p id="feedback-text" aria-live="assertive"></p>
      <div id="explanations">
        <!-- Explanations will be shown here -->
      </div>
    </div>
  </main>
</div>
`;

// Mock global window methods
window.fetch = jest.fn();
window.EventSource = jest.fn();

// Sample test data
const sampleStatements = [
  { text: "Truth statement 1", isLie: false, explanation: "Truth explanation 1" },
  { text: "Truth statement 2", isLie: false, explanation: "Truth explanation 2" },
  { text: "Lie statement", isLie: true, explanation: "Lie explanation" }
];

// Import the script
const scriptCode = require('../src/static/script.js');

// Test suite
describe('Two Truths & AI Game Frontend', () => {
  let statementsContainer, feedbackArea, feedbackText, explanationsContainer, 
      nextRoundButton, correctScoreSpan, incorrectScoreSpan, roundsPlayedSpan, flashFeedback;
  
  beforeEach(() => {
    // Reset DOM elements before each test
    statementsContainer = document.getElementById('statements-container');
    feedbackArea = document.getElementById('feedback-area');
    feedbackText = document.getElementById('feedback-text');
    explanationsContainer = document.getElementById('explanations');
    nextRoundButton = document.getElementById('next-round-button');
    correctScoreSpan = document.getElementById('correct-score');
    incorrectScoreSpan = document.getElementById('incorrect-score');
    roundsPlayedSpan = document.getElementById('rounds-played');
    flashFeedback = document.getElementById('flash-feedback');
    
    // Reset mock functions
    fetch.mockClear();
    EventSource.mockClear();
  });
  
  test('Should show loading indicator when waiting for round', () => {
    // Call the showLoadingIndicator function
    showLoadingIndicator();
    
    // Check that the loading indicator is displayed
    expect(statementsContainer.innerHTML).toContain('spinner');
    expect(statementsContainer.innerHTML).toContain('loading-content');
  });
  
  test('Should handle and display new round data correctly', () => {
    // Set up current statements
    currentStatements = sampleStatements;
    
    // Call the displayStatements function
    displayStatements();
    
    // Check that the statements are displayed as buttons
    const buttons = statementsContainer.querySelectorAll('.statement-button');
    expect(buttons.length).toBe(3);
    
    // Check that all statements are present
    const buttonTexts = Array.from(buttons).map(button => button.textContent);
    expect(buttonTexts).toContain(sampleStatements[0].text);
    expect(buttonTexts).toContain(sampleStatements[1].text);
    expect(buttonTexts).toContain(sampleStatements[2].text);
  });
  
  test('Should handle statement selection and show feedback', () => {
    // Set up current statements
    currentStatements = sampleStatements;
    gameInProgress = true;
    
    // Display the statements
    displayStatements();
    
    // Get the statement buttons
    const buttons = statementsContainer.querySelectorAll('.statement-button');
    
    // Click on a truth statement (incorrect choice)
    buttons[0].click();
    
    // Check that game progress is stopped
    expect(gameInProgress).toBe(false);
    
    // Check that score is updated
    expect(incorrectScoreSpan.textContent).toBe('1');
    expect(correctScoreSpan.textContent).toBe('0');
    expect(roundsPlayedSpan.textContent).toBe('1');
    
    // Check that feedback is shown
    expect(feedbackArea.classList.contains('hidden')).toBe(false);
    expect(nextRoundButton.classList.contains('hidden')).toBe(false);
    expect(feedbackText.textContent).toContain('Incorrect');
  });
  
  test('Should trigger flash feedback animation', () => {
    // Call triggerFlashFeedback for correct guess
    triggerFlashFeedback(true);
    
    // Check that flash feedback is configured correctly
    expect(flashFeedback.textContent).toBe('You are smart AF!');
    
    // For incorrect guess
    triggerFlashFeedback(false);
    
    // Check that flash feedback is updated
    expect(flashFeedback.textContent).toBe('You are dumb AF!');
  });
  
  test('Should display explanations after selection', () => {
    // Set up current statements and display order
    currentStatements = sampleStatements;
    window.displayedStatementOrder = [...sampleStatements];
    
    // Call displayExplanations
    displayExplanations();
    
    // Check that explanations are displayed
    const explanationElements = explanationsContainer.querySelectorAll('p');
    expect(explanationElements.length).toBe(3);
    
    // Check content of explanations
    const truthExplanations = explanationsContainer.querySelectorAll('.true-explanation');
    const lieExplanations = explanationsContainer.querySelectorAll('.false-explanation');
    expect(truthExplanations.length).toBe(2);
    expect(lieExplanations.length).toBe(1);
  });
  
  test('Should request new round when button is clicked', () => {
    // Set up fetch mock to resolve
    fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ message: "New round generation triggered" })
    });
    
    // Click the next round button
    nextRoundButton.addEventListener('click', requestNewRound);
    nextRoundButton.click();
    
    // Check that fetch was called with correct URL
    expect(fetch).toHaveBeenCalledWith('/api/trigger_new_round');
    
    // Check that loading indicator is shown
    expect(statementsContainer.innerHTML).toContain('spinner');
  });
  
  test('Should handle server errors correctly', () => {
    // Call handleServerError with a test message
    handleServerError("Test error message");
    
    // Check that error is displayed
    expect(statementsContainer.innerHTML).toContain('Test error message');
    expect(statementsContainer.innerHTML).toContain('statement-placeholder error');
    
    // Check that game is stopped
    expect(gameInProgress).toBe(false);
  });
});