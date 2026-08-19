import fs from "node:fs";
import path from "node:path";
import { marked } from "marked";
import {
  getAllConfidenceScores,
  getDailyFailureRate,
  getLatestEvalRun,
  getReviewQueue,
} from "./db";

export const dynamic = "force-dynamic";

const HISTOGRAM_BUCKETS = [
  [0.0, 0.1], [0.1, 0.2], [0.2, 0.3], [0.3, 0.4], [0.4, 0.5],
  [0.5, 0.6], [0.6, 0.7], [0.7, 0.8], [0.8, 0.9], [0.9, 1.01],
] as const;

function bucketize(scores: number[]) {
  return HISTOGRAM_BUCKETS.map(([lo, hi]) => ({
    label: `${lo.toFixed(1)}–${Math.min(hi, 1).toFixed(1)}`,
    count: scores.filter((s) => s >= lo && s < hi).length,
  }));
}

function statusForConfidence(confidence: number): "good" | "warning" | "critical" {
  if (confidence >= 0.7) return "good";
  if (confidence >= 0.4) return "warning";
  return "critical";
}

// Local-dev-only fallback: reads the sibling eval/eval_report.md file directly.
// Works when running `npm run dev` from a full checkout (dashboard/ and eval/
// side by side), but is NOT relied on in production -- a deployment with
// Root Directory=dashboard (e.g. Vercel) won't have eval/ available at
// runtime at all. The DB-stored report_markdown column (see db.ts) is the
// source of truth; this is only consulted if that's empty.
function readEvalReportFromDisk(): string | null {
  const reportPath = path.join(process.cwd(), "..", "eval", "eval_report.md");
  try {
    return fs.readFileSync(reportPath, "utf-8");
  } catch {
    return null;
  }
}

export default async function DashboardPage() {
  let confidenceScores: number[] = [];
  let dailyStats: Awaited<ReturnType<typeof getDailyFailureRate>> = [];
  let reviewQueue: Awaited<ReturnType<typeof getReviewQueue>> = [];
  let latestEvalRun: Awaited<ReturnType<typeof getLatestEvalRun>> = null;
  let dbError: string | null = null;

  try {
    const [scores, daily, queue, evalRun] = await Promise.all([
      getAllConfidenceScores(),
      getDailyFailureRate(),
      getReviewQueue(),
      getLatestEvalRun(),
    ]);
    confidenceScores = scores.map((r) => r.confidence);
    dailyStats = daily;
    reviewQueue = queue;
    latestEvalRun = evalRun;
  } catch (e) {
    dbError = e instanceof Error ? e.message : String(e);
  }

  const evalReportMarkdown = latestEvalRun?.report_markdown ?? readEvalReportFromDisk();
  const evalReportHtml = evalReportMarkdown ? marked.parse(evalReportMarkdown, { async: false }) : null;

  const buckets = bucketize(confidenceScores);
  const maxBucketCount = Math.max(1, ...buckets.map((b) => b.count));
  const totalMessages = confidenceScores.length;
  const flaggedTotal = dailyStats.reduce((sum, d) => sum + d.flagged, 0);
  const overallFailureRate = totalMessages > 0 ? flaggedTotal / totalMessages : null;

  return (
    <main>
      <header className="page-header">
        <div className="titles">
          <h1>Confidence-Gated Intake</h1>
          <p className="subtitle">Extraction accuracy and confidence, measured, not asserted.</p>
        </div>
        <div className="badge-live">
          <span className="dot" />
          Live
        </div>
      </header>

      {dbError && (
        <div className="error-banner">
          <span className="dot" />
          <span>
            Could not reach the database (<code>{dbError}</code>). Showing whatever else is
            available below.
          </span>
        </div>
      )}

      <section>
        <div className="stat-row">
          <div className="stat">
            <div className="label">Total messages processed</div>
            <div className="value">{totalMessages}</div>
          </div>
          <div className="stat">
            <div className="label">Routed to review queue</div>
            <div className={`value ${overallFailureRate === null ? "dim" : ""}`}>
              {overallFailureRate !== null ? `${(overallFailureRate * 100).toFixed(1)}%` : "—"}
            </div>
          </div>
          <div className="stat">
            <div className="label">Latest eval accuracy</div>
            <div className={`value ${!latestEvalRun ? "dim" : ""}`}>
              {latestEvalRun ? `${(latestEvalRun.accuracy * 100).toFixed(1)}%` : "—"}
            </div>
          </div>
          <div className="stat">
            <div className="label">False-confidence count</div>
            <div className={`value ${!latestEvalRun ? "dim" : ""}`}>
              {latestEvalRun ? latestEvalRun.false_confidence_count : "—"}
            </div>
          </div>
        </div>
      </section>

      <section className="grid-2">
        <div>
          <div className="section-head">
            <h2>Confidence distribution</h2>
            {totalMessages > 0 && <span className="section-meta">{totalMessages} messages</span>}
          </div>
          <div className="panel">
            {totalMessages === 0 ? (
              <div className="empty">No messages processed yet.</div>
            ) : (
              <div className="histogram">
                {buckets.map((b) => (
                  <div key={b.label} className="col">
                    <span className="bar-count">{b.count}</span>
                    <div className="bar-track">
                      <div
                        className="bar"
                        style={{
                          height: b.count > 0 ? `${Math.max((b.count / maxBucketCount) * 100, 4)}%` : "0",
                        }}
                      />
                    </div>
                    <div className="bar-label">{b.label}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div>
          <div className="section-head">
            <h2>Failure rate over time</h2>
          </div>
          <div className="panel">
            {dailyStats.length === 0 ? (
              <div className="empty">No data yet.</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Total</th>
                    <th>Flagged</th>
                    <th>Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {dailyStats.map((d) => (
                    <tr key={d.day}>
                      <td className="num">{d.day}</td>
                      <td className="num">{d.total}</td>
                      <td className="num">{d.flagged}</td>
                      <td className="num">{((d.flagged / d.total) * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </section>

      <section>
        <div className="section-head">
          <h2>Review queue</h2>
          <span className="section-meta">{reviewQueue.length} unresolved</span>
        </div>
        <div className="panel">
          {reviewQueue.length === 0 ? (
            <div className="empty">Nothing waiting on human review.</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Confidence</th>
                  <th>Extracted (best effort)</th>
                  <th>Reason</th>
                  <th>Received</th>
                </tr>
              </thead>
              <tbody>
                {reviewQueue.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <span className={`badge ${statusForConfidence(r.confidence)}`}>
                        {(r.confidence * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td>
                      {r.extracted_json?.customer_name ?? "—"} ·{" "}
                      {r.extracted_json?.request_type ?? "—"} ·{" "}
                      {r.extracted_json?.urgency ?? "—"}
                    </td>
                    <td>{r.reason ?? "—"}</td>
                    <td className="num">{new Date(r.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section>
        <div className="section-head">
          <h2>Evaluation report</h2>
        </div>
        <div className="panel">
          {evalReportHtml ? (
            <div className="eval-report" dangerouslySetInnerHTML={{ __html: evalReportHtml }} />
          ) : (
            <div className="empty">
              No eval report yet. Run <code>cd eval && python3 run_eval.py</code>.
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
