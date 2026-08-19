import { Pool } from "pg";

declare global {
  // eslint-disable-next-line no-var
  var __intakePool: Pool | undefined;
}

const DATABASE_URL =
  process.env.DATABASE_URL ?? "postgresql://pranaysb@localhost:5432/intake";

// Reuse the pool across hot reloads in dev instead of opening a new one per request.
export const pool = global.__intakePool ?? new Pool({ connectionString: DATABASE_URL });
if (process.env.NODE_ENV !== "production") {
  global.__intakePool = pool;
}

export type ConfidenceRow = { confidence: number; created_at: string };

export type ReviewQueueRow = {
  id: string;
  message_id: string;
  extracted_json: Record<string, string | null>;
  confidence: number;
  reason: string | null;
  resolved: boolean;
  created_at: string;
};

export type DailyStats = { day: string; total: number; flagged: number };

export async function getAllConfidenceScores(): Promise<ConfidenceRow[]> {
  const { rows } = await pool.query<ConfidenceRow>(`
    select confidence, created_at from tickets
    union all
    select confidence, created_at from review_queue
    order by created_at asc
  `);
  return rows;
}

export async function getDailyFailureRate(): Promise<DailyStats[]> {
  const { rows } = await pool.query<DailyStats>(`
    with combined as (
      select created_at, false as flagged from tickets
      union all
      select created_at, true as flagged from review_queue
    )
    select
      to_char(date_trunc('day', created_at), 'YYYY-MM-DD') as day,
      count(*)::int as total,
      count(*) filter (where flagged)::int as flagged
    from combined
    group by 1
    order by 1 asc
  `);
  return rows;
}

export async function getReviewQueue(): Promise<ReviewQueueRow[]> {
  const { rows } = await pool.query<ReviewQueueRow>(`
    select id, message_id, extracted_json, confidence, reason, resolved, created_at
    from review_queue
    where resolved = false
    order by created_at desc
    limit 100
  `);
  return rows;
}

export async function getLatestEvalRun() {
  const { rows } = await pool.query(`
    select total_messages, correct_extractions, false_confidence_count, accuracy, run_at
    from eval_runs
    order by run_at desc
    limit 1
  `);
  return rows[0] ?? null;
}
