import fs from "node:fs";
import path from "node:path";
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

function confidenceBadgeClass(confidence: number) {
  if (confidence >= 0.7) return "high";
  if (confidence >= 0.4) return "mid";
  return "low";
}

function readEvalReport(): string | null {
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

  const evalReport = readEvalReport();
  const buckets = bucketize(confidenceScores);
  const maxBucketCount = Math.max(1, ...buckets.map((b) => b.count));
  const totalMessages = confidenceScores.length;
  const flaggedTotal = dailyStats.reduce((sum, d) => sum + d.flagged, 0);
  const overallFailureRate = totalMessages > 0 ? flaggedTotal / totalMessages : null;

  return (
    <main>
      <h1>Confidence-Gated Intake</h1>
      <p className="subtitle">Extraction accuracy and confidence, measured, not asserted.</p>

      {dbError && (
        <div className="panel" style={{ borderColor: "var(--bad)", marginBottom: 24 }}>
          Could not reach the database ({dbError}). Is <code>docker compose up</code> running?
          Showing whatever else is available below.
        </div>
      )}

      <section>
        <h2>Summary</h2>
        <div className="stat-row">
          <div className="stat">
            <div className="value">{totalMessages}</div>
            <div className="label">total messages processed</div>
          </div>
          <div className="stat">
            <div className="value">
              {overallFailureRate !== null ? `${(overallFailureRate * 100).toFixed(1)}%` : "—"}
            </div>
            <div className="label">routed to review queue</div>
          </div>
          <div className="stat">
            <div className="value">
              {latestEvalRun ? `${(latestEvalRun.accuracy * 100).toFixed(1)}%` : "—"}
            </div>
            <div className="label">latest eval accuracy</div>
          </div>
          <div className="stat">
            <div className="value">{latestEvalRun ? latestEvalRun.false_confidence_count : "—"}</div>
            <div className="label">false-confidence count (latest eval)</div>
          </div>
        </div>
      </section>

      <section>
        <h2>Confidence distribution</h2>
        <div className="panel">
          {totalMessages === 0 ? (
            <div className="empty">No messages processed yet.</div>
          ) : (
            <div style={{ display: "flex", alignItems: "flex-end", gap: 8, height: 140 }}>
              {buckets.map((b) => (
                <div key={b.label} style={{ flex: 1, textAlign: "center" }}>
                  <div
                    title={`${b.count} messages`}
                    style={{
                      height: `${(b.count / maxBucketCount) * 110}px`,
                      background: "var(--accent)",
                      borderRadius: "3px 3px 0 0",
                      minHeight: b.count > 0 ? 3 : 0,
                    }}
                  />
                  <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 6 }}>{b.label}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section>
        <h2>Failure rate over time</h2>
        <div className="panel">
          {dailyStats.length === 0 ? (
            <div className="empty">No data yet.</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Day</th>
                  <th>Total</th>
                  <th>Flagged for review</th>
                  <th>Rate</th>
                </tr>
              </thead>
              <tbody>
                {dailyStats.map((d) => (
                  <tr key={d.day}>
                    <td>{d.day}</td>
                    <td>{d.total}</td>
                    <td>{d.flagged}</td>
                    <td>{((d.flagged / d.total) * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section>
        <h2>Review queue ({reviewQueue.length} unresolved)</h2>
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
                      <span className={`badge ${confidenceBadgeClass(r.confidence)}`}>
                        {(r.confidence * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td>
                      {r.extracted_json?.customer_name ?? "—"} ·{" "}
                      {r.extracted_json?.request_type ?? "—"} ·{" "}
                      {r.extracted_json?.urgency ?? "—"}
                    </td>
                    <td>{r.reason ?? "—"}</td>
                    <td>{new Date(r.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section>
        <h2>Evaluation report</h2>
        <div className="panel">
          {evalReport ? (
            <pre className="eval-report">{evalReport}</pre>
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
