// Called by actions/github-script via require().
// Files:    coverage.xml                         (pytest-cov)
//           coverage/js/coverage-summary.json    (vitest --coverage, json-summary)
//           coverage/js/cobertura-coverage.xml   (vitest --coverage, cobertura — fed to diff-cover)
//           junit/test-results.xml               (pytest --junitxml)
//           junit/js-test-results.xml            (vitest junit reporter)
//           diff-coverage.json                   (diff-cover --json-report, covers py + js)

const fs = require("fs");

function coverageColor(pct) {
    if (pct >= 90) return "brightgreen";
    if (pct >= 80) return "green";
    if (pct >= 70) return "yellow";
    if (pct >= 60) return "orange";
    return "red";
}

function pyCoverageLines() {
    if (!fs.existsSync("coverage.xml")) return null;
    const xml = fs.readFileSync("coverage.xml", "utf8");
    const valid = xml.match(/lines-valid="([0-9]+)"/);
    const covered = xml.match(/lines-covered="([0-9]+)"/);
    if (!valid || !covered) return null;
    return { total: parseInt(valid[1], 10), covered: parseInt(covered[1], 10) };
}

function jsCoverageLines() {
    if (!fs.existsSync("coverage/js/coverage-summary.json")) return null;
    const summary = JSON.parse(fs.readFileSync("coverage/js/coverage-summary.json", "utf8"));
    const lines = summary.total?.lines;
    if (!lines) return null;
    return { total: lines.total, covered: lines.covered };
}

function linesToPct(lines) {
    return lines && lines.total > 0 ? Math.round((lines.covered / lines.total) * 100) : null;
}

function pyCoveragePct() { return linesToPct(pyCoverageLines()); }
function jsCoveragePct() { return linesToPct(jsCoverageLines()); }

function totalCoveragePct() {
    const py = pyCoverageLines();
    const js = jsCoverageLines();
    if (!py && !js) return null;
    const total = (py?.total ?? 0) + (js?.total ?? 0);
    const covered = (py?.covered ?? 0) + (js?.covered ?? 0);
    return total > 0 ? Math.round((covered / total) * 100) : null;
}

function coverageBadge(label, pct) {
    if (pct == null) return "";
    const slug = label.replace(/ /g, "%20");
    return `![${label}](https://img.shields.io/badge/${slug}-${pct}%25-${coverageColor(pct)})`;
}

// Sums stats across all <testsuite> elements — works for both pytest and vitest JUnit XML.
function parseJUnit(path) {
    if (!fs.existsSync(path)) return null;
    const xml = fs.readFileSync(path, "utf8");
    let tests = 0, skipped = 0, failures = 0, errors = 0, time = 0;
    for (const m of xml.matchAll(/<testsuite\b([^>]*)>/g)) {
        const attr = (name) => { const a = m[1].match(new RegExp(`\\b${name}="([^"]+)"`)); return a ? a[1] : "0"; };
        tests += parseInt(attr("tests"), 10);
        skipped += parseInt(attr("skipped"), 10);
        failures += parseInt(attr("failures"), 10);
        errors += parseInt(attr("errors"), 10);
        time += parseFloat(attr("time") || "0");
    }
    return { tests, skipped, failures, errors, time };
}

function buildSummaryTable(pyPath, jsPath) {
    const py = parseJUnit(pyPath);
    const js = parseJUnit(jsPath);
    if (!py && !js) return "";

    const rows = [];
    if (py) rows.push(`| Python | ${py.tests} | ${py.skipped} | ${py.failures} | ${py.errors} | ${py.time.toFixed(3)}s |`);
    if (js) rows.push(`| JS     | ${js.tests} | ${js.skipped} | ${js.failures} | ${js.errors} | ${js.time.toFixed(3)}s |`);

    const tot = { tests: 0, skipped: 0, failures: 0, errors: 0 };
    for (const s of [py, js].filter(Boolean)) {
        tot.tests += s.tests; tot.skipped += s.skipped; tot.failures += s.failures; tot.errors += s.errors;
    }
    rows.push(`| **Total** | **${tot.tests}** | **${tot.skipped}** | **${tot.failures}** | **${tot.errors}** | |`);

    return [
        "| Suite | Tests | Skipped | Failures | Errors | Time |",
        "|-------|------:|--------:|---------:|-------:|------|",
        ...rows,
    ].join("\n");
}

module.exports = async ({ github, context }) => {
    const py = pyCoveragePct();
    const js = jsCoveragePct();
    const total = totalCoveragePct();
    const badges = [coverageBadge("Total Coverage", total), coverageBadge("Python Coverage", py), coverageBadge("JS Coverage", js)]
        .filter(Boolean).join("  ");

    let diffBadge = "";
    let diffTable = "";
    if (fs.existsSync("diff-coverage.json")) {
        const diff = JSON.parse(fs.readFileSync("diff-coverage.json", "utf8"));
        const rawDiffPct = Number(diff.total_percent_covered ?? 0);
        const diffPct = Number.isFinite(rawDiffPct) ? rawDiffPct : 0;
        diffBadge = `  ![Diff Coverage](https://img.shields.io/badge/Diff%20Coverage-${Math.round(diffPct)}%25-${coverageColor(diffPct)})`;

        const repoUrl = `https://github.com/${context.repo.owner}/${context.repo.repo}/blob/${context.sha}`;
        const rows = Object.entries(diff.src_stats)
            .filter(([, s]) => s.covered_lines.length + s.violation_lines.length > 0)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([file, s]) => {
                const nLines = s.covered_lines.length + s.violation_lines.length;
                const nMiss = s.violation_lines.length;
                const pct = Math.round(s.percent_covered);
                const missing = s.violation_lines.length
                    ? s.violation_lines
                        .map((l) => `<a href="${repoUrl}/${file}#L${l}">${l}</a>`)
                        .join(", ")
                    : "&nbsp;";
                const shortFile = file.replace(/^app\//, "");
                return `<tr><td><a href="${repoUrl}/${file}">${shortFile}</a></td><td>${nLines}</td><td>${nMiss}</td><td>${pct}%</td><td>${missing}</td></tr>`;
            });

        if (rows.length > 0) {
            const totalStmts = diff.total_num_lines ?? 0;
            const totalMiss = diff.total_num_violations ?? 0;
            const totalPct = Math.round(diffPct);
            const totalRow = `<tr><td><b>TOTAL</b></td><td><b>${totalStmts}</b></td><td><b>${totalMiss}</b></td><td><b>${totalPct}%</b></td><td>&nbsp;</td></tr>`;
            diffTable = `<details><summary>Diff Coverage Report </summary><table><tr><th>File</th><th>Stmts</th><th>Miss</th><th>Cover</th><th>Missing</th></tr><tbody>${rows.join("")}${totalRow}</tbody></table></details>`;
        }
    }

    const summaryTable = buildSummaryTable("junit/test-results.xml", "junit/js-test-results.xml");

    const body = [
        "<!-- coverage-report -->",
        `${badges}${diffBadge}`,
        "",
        summaryTable,
        "",
        diffTable,
    ].join("\n");

    const { data: comments } = await github.rest.issues.listComments({
        owner: context.repo.owner,
        repo: context.repo.repo,
        issue_number: context.issue.number,
    });

    const existing = comments.find(
        (c) => c.body && c.body.includes("<!-- coverage-report -->"),
    );
    if (existing) {
        await github.rest.issues.updateComment({
            owner: context.repo.owner,
            repo: context.repo.repo,
            comment_id: existing.id,
            body,
        });
    } else {
        await github.rest.issues.createComment({
            owner: context.repo.owner,
            repo: context.repo.repo,
            issue_number: context.issue.number,
            body,
        });
    }
};
