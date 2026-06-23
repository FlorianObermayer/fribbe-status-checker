import { defineConfig } from 'vitest/config';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const { readThreshold } = require('./.github/scripts/coverage-utils.js');
const coverageThreshold = readThreshold('tool.coverage.report');

export default defineConfig({
    test: {
        environment: 'jsdom',
        include: ['tests/js/**/*.test.js'],
        reporters: ['default', 'junit'],
        outputFile: { junit: 'junit/js-test-results.xml' },
        coverage: {
            provider: 'v8',
            include: ['app/static/js/**/*.js'],
            reporter: ['json-summary', 'cobertura'],
            reportsDirectory: 'coverage/js',
            thresholds: { lines: coverageThreshold },
        },
    },
});
