const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.',
  testMatch: /agent-demo\.spec\.js/,
  timeout: 60000,
  use: {
    viewport: { width: 1440, height: 1000 },
  },
});
