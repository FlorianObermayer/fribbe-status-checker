// Shared coverage utilities used by:
//   coverage-comment.js  (require)
//   vitest.config.js     (createRequire)
//   ci-cd.yml            (node -e … require('./.github/scripts/coverage-utils.js'))

const fs = require("fs");

// Reads fail_under from a [tool.*] section in pyproject.toml. Falls back to 80.
function readThreshold(section) {
    try {
        const toml = fs.readFileSync("pyproject.toml", "utf8");
        const escaped = section.replace(/\./g, "\\.");
        const m = toml.match(new RegExp(`\\[${escaped}\\]([\\s\\S]*?)(?=\\n\\[|$)`));
        if (!m) throw new Error(`Section [${section}] not found in pyproject.toml`);
        const v = m[1].match(/^fail_under\s*=\s*(\d+)/m);
        return v ? parseInt(v[1], 10) : 80;
    } catch (error) {
        throw new Error(`Failed to read [${section}] fail_under from pyproject.toml: ${error.message}`);
    }
}

// Colors relative to the enforcement threshold:
//   red         = below threshold (failing)
//   orange/yellow/green/brightgreen = linearly spaced across [threshold, 100]
function coverageColor(pct, threshold) {
    if (pct < threshold) return "red";
    const step = (100 - threshold) / 4;
    if (pct >= threshold + 3 * step) return "brightgreen";
    if (pct >= threshold + 2 * step) return "green";
    if (pct >= threshold + step)     return "yellow";
    return "orange";
}

module.exports = { readThreshold, coverageColor };
