import { defineConfig } from 'vitest/config';

export default defineConfig({
    test: {
        environment: 'jsdom',
        include: ['tests/js/**/*.test.js', '.github/tests/js/**/*.test.js'],
        reporters: ['default', 'junit'],
        outputFile: { junit: 'junit/js-test-results.xml' },
        coverage: {
            provider: 'v8',
            include: ['app/static/js/**/*.js', '.github/scripts/**/*.js', 'scripts/**/*.js'],
            reporter: ['json-summary', 'cobertura', 'text'],
            reportsDirectory: 'coverage/js'
        },
    },
});
