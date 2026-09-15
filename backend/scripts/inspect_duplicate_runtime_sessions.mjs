/** Read-only evidence for the operator's two explicitly selected Pro sessions. */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const native = path.join(root, 'openmaic-runtime/.runtime/OpenMAIC');
const require = createRequire(path.join(native, 'package.json'));
const { Client } = require('pg');
const { qualitySnapshot } = require(path.join(native, 'lib/server/mira-formal-quality-contract.ts'));
const ids = process.argv.slice(2);
if (ids.length !== 2 || new Set(ids).size !== 2 || ids.some(id => !/^miraformal_[a-f0-9]{64}$/.test(id)))
  throw new Error('DUPLICATE_RECOVERY_SESSION_ID_INVALID');
const client = new Client({ connectionString: process.env.MIRA_OPENMAIC_AGENT_DATABASE_URL });
await client.connect();
try {
  await client.query('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');
  await client.query("SET LOCAL statement_timeout='10000ms'");
  const evidence = [];
  for (const id of ids) {
    const session = (await client.query(`SELECT id,owner_id,status,attempt,error,
      stage_id,active_stage_id,cancel_requested_at,lease_worker_id,deleted_at
      FROM agent_sessions WHERE id=$1`, [id])).rows[0];
    if (!session) throw new Error('DUPLICATE_RECOVERY_SESSION_MISSING');
    const stages = (await client.query('SELECT id,data FROM document_stages WHERE owner_id=$1 ORDER BY id', [session.owner_id])).rows;
    const scenes = (await client.query('SELECT stage_id,data FROM document_scenes WHERE stage_id=ANY($1::text[]) ORDER BY stage_id,scene_order,id', [stages.map(s => s.id)])).rows;
    // Hash model/tool payloads in PostgreSQL. Streaming deltas can be enormous;
    // their durable ordered references remain auditable without copying bodies.
    const events = (await client.query(`SELECT seq,type,ts,attempt,
      encode(sha256(convert_to(data::text,'UTF8')),'hex') AS data_sha256,
      CASE WHEN type IN ('session_end','stage_link','course_link') THEN data ELSE NULL END AS data
      FROM agent_session_events WHERE session_id=$1 ORDER BY seq`, [id])).rows;
    const ownerEvents = (await client.query(`SELECT id,session_id,type,status,attempt,ts,
      encode(sha256(convert_to(data::text,'UTF8')),'hex') AS data_sha256
      FROM agent_owner_session_events WHERE owner_id=$1 AND session_id=$2 ORDER BY id`, [session.owner_id,id])).rows;
    evidence.push({ session, stageCount: stages.length, sceneCount: scenes.length, events, ownerEvents,
      snapshot: stages.length === 1 && scenes.length ? qualitySnapshot(stages[0].data, scenes.map(s => s.data)) : null });
  }
  await client.query('ROLLBACK');
  process.stdout.write(JSON.stringify(evidence));
} finally { await client.end(); }
