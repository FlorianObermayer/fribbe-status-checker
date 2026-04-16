// Called by actions/github-script via require().
// Env vars: SUMMARY_REPORT, GLOBAL_PCT, GLOBAL_COLOR
// File: diff-coverage.json (written by diff-cover --json-report)

const fs = require("fs");

module.exports = async ({ github, context }) => {
    const globalPct = encodeURIComponent(process.env.GLOBAL_PCT || "0%");
    const globalColor = process.env.GLOBAL_COLOR || "red";
    const globalBadge = `![Coverage](https://img.shields.io/badge/Coverage-${globalPct}-${globalColor})`;

    let diffBadge = "";
    let diffTable = "";
    if (fs.existsSync("diff-coverage.json")) {
        const diff = JSON.parse(fs.readFileSync("diff-coverage.json", "utf8"));
        const rawDiffPct = Number(diff.total_percent_covered ?? 0);
        const diffPct = Number.isFinite(rawDiffPct) ? rawDiffPct : 0;
        const diffColor =
            diffPct >= 95
                ? "brightgreen"
                : diffPct >= 90
                    ? "green"
                    : diffPct >= 85
                        ? "yellow"
                        : diffPct >= 80
                            ? "orange"
                            : "red";
        diffBadge = `  ![Diff Coverage](https://img.shields.io/badge/Diff%20Coverage-${Math.round(diffPct)}%25-${diffColor})`;

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

    // summaryReport is passed as a JSON-encoded string with literal \n — parse it
    // MishaKav prepends a badge + full coverage <details> table; extract only the | Tests | summary row
    let summaryReport = "";
    try {
        const raw = process.env.SUMMARY_REPORT || "";
        const decoded = raw.startsWith('"') ? JSON.parse(raw) : raw;
        const match = decoded.match(/(\| Tests \|[\s\S]*)/);
        summaryReport = match ? match[1].trim() : decoded.trim();
    } catch (_) { }

    const body = [
        "<!-- coverage-report -->",
        `${globalBadge}${diffBadge}`,
        "",
        summaryReport,
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
