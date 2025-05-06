/**
 * Jest configuration for frontend testing
 */
module.exports = {
  verbose: true,
  testEnvironment: 'jsdom',
  testMatch: ['**/tests/test_frontend.js'],
  collectCoverage: true,
  collectCoverageFrom: ['src/static/script.js'],
  coverageDirectory: 'coverage',
  transform: {
    '^.+\\.js$': 'babel-jest',
  },
  moduleNameMapper: {
    '\\.(css|less|scss|sass)$': '<rootDir>/tests/mocks/styleMock.js',
    '\\.(jpg|jpeg|png|gif|webp|svg)$': '<rootDir>/tests/mocks/fileMock.js',
  },
  setupFiles: ['<rootDir>/tests/setup.js'],
};