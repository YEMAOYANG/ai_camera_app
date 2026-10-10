#!/usr/bin/env -S node --import tsx
/** Isolated native OpenMAIC page-generation comparison; default is provider-free.
 * Run with Node 24 and the native checkout's tsx. No AppConfig, DB, server route,
 * publication, media generation, TTS, fallback model or automatic paid retry.
 */
import { createHash } from 'node:crypto';
import { chmod, mkdir, open, readFile, readdir, realpath, rename, stat } from 'node:fs/promises';
import { dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { Script } from 'node:vm';

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
export const NATIVE = join(ROOT, 'openmaic-runtime/.runtime/OpenMAIC');
export const OUTPUT_ROOT = join(ROOT, 'backend/data/homework/course-evals');
export const MAX_CALLS = 68;
export const MAX_INPUT_BYTES = 80_000;
export const MAX_OUTPUT_TOKENS = 16_000;
export const MAX_USD = 8;
export const ENDPOINT = 'https://api.deepseek.com/v1/chat/completions';
export const CANDIDATES = [
  { id: 'pro', model: 'deepseek-v4-pro', inputUsdPerMillion: 1.32, outputUsdPerMillion: 3.96 },
  { id: 'flash', model: 'deepseek-flash', inputUsdPerMillion: 0.30, outputUsdPerMillion: 1.20 },
] as const;
const SKILL_IDS = ['mira-primary-courseware', 'stage-design', 'k12-core-literacy-planning', 'deep-interactive', 'slide-craft', 'learning-to-learn'];
const TYPES = new Set(['slide', 'quiz', 'interactive']);
const WIDGETS = new Set(['simulation', 'diagram', 'code', 'game', 'visualization3d']);
type Candidate = typeof CANDIDATES[number];
type Phase = 'plan' | 'content' | 'actions';
type Json = Record<string, any>;
export type Fetcher = (url: string, init: RequestInit) => Promise<Response>;

export function sha(value: string | Buffer): string { return createHash('sha256').update(value).digest('hex'); }
function canonical(value: any): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
export function inputBytes(messages: unknown): number { return Buffer.byteLength(JSON.stringify(messages), 'utf8'); }
export function reservedUsd(candidate: Candidate, bytes: number): number {
  // UTF-8 bytes are the conservative input token bound, with no cache discount.
  return (bytes * candidate.inputUsdPerMillion + MAX_OUTPUT_TOKENS * candidate.outputUsdPerMillion) / 1_000_000;
}
export async function save(path: string, value: unknown): Promise<void> {
  const temp = path + '.pending';
  const fd = await open(temp, 'w', 0o600);
  try { await fd.writeFile(JSON.stringify(value, null, 2)); await fd.sync(); } finally { await fd.close(); }
  await rename(temp, path); await chmod(path, 0o600);
}
async function exists(path: string): Promise<boolean> {
  try { await stat(path); return true; } catch (e: any) { if (e.code === 'ENOENT') return false; throw e; }
}
async function append(path: string, row: unknown): Promise<void> {
  const fd = await open(path, 'a', 0o600);
  try { await fd.writeFile(JSON.stringify(row) + '\n'); await fd.sync(); } finally { await fd.close(); }
}
function within(parent: string, path: string): boolean {
  const rel = relative(parent, path); return !!rel && !rel.startsWith('../') && rel !== '..' && !isAbsolute(rel);
}
async function treeHashes(base: string): Promise<Json[]> {
  const rows: Json[] = [];
  async function visit(folder: string) {
    for (const item of (await readdir(folder, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
      const path = join(folder, item.name);
      if (item.isSymbolicLink()) throw new Error('source_symlink_not_allowed');
      if (item.isDirectory()) await visit(path);
      else if (item.isFile()) rows.push({ path: relative(ROOT, path), sha256: sha(await readFile(path)) });
    }
  }
  await visit(base); return rows;
}
export function validateSpec(spec: Json): void {
  if (!Array.isArray(spec.courses) || spec.courses.length !== 2) throw new Error('exactly_two_courses_required');
  if (new Set(spec.courses.map((c: Json) => c.id)).size !== 2 || new Set(spec.courses.map((c: Json) => c.subject)).size !== 2) throw new Error('two_distinct_courses_and_subjects_required');
  for (const course of spec.courses) {
    if (!/^[a-zA-Z0-9_-]{1,80}$/.test(course.id) || !['primary_1', 'primary_2'].includes(course.gradeCode) || !['chinese', 'math', 'english'].includes(course.subject)) throw new Error('unsupported_course_scope');
    if (typeof course.requirements?.requirement !== 'string' || !course.requirements.requirement.trim()) throw new Error('course_requirement_required');
    if (course.requirements.webSearch !== false) throw new Error('web_search_must_be_disabled');
  }
  if (spec.sharedMedia !== undefined && !Array.isArray(spec.sharedMedia)) throw new Error('invalid_media_list');
}
function section(text: string, title: string): string {
  const start = text.indexOf('\n## ' + title); if (start < 0) return '';
  const end = text.indexOf('\n## ', start + 1); return text.slice(start + 1, end < 0 ? undefined : end).trim();
}
export async function freeze(specPath: string, candidates: readonly Candidate[] = CANDIDATES): Promise<{ manifest: Json; spec: Json; skills: Record<string, string> }> {
  const bytes = await readFile(specPath); const spec = JSON.parse(bytes.toString('utf8')); validateSpec(spec);
  const packageRoot = join(NATIVE, 'packages/@openmaic/generation');
  const hashes = [
    ...(await treeHashes(join(packageRoot, 'src'))), ...(await treeHashes(join(packageRoot, 'dist'))),
    ...(await treeHashes(join(packageRoot, 'templates'))), ...(await treeHashes(join(packageRoot, 'snippets'))),
    ...(await treeHashes(join(NATIVE, 'packages/@openmaic/dsl/dist'))),
  ];
  for (const name of ['lib/server/mira-formal-learning-contract.ts', 'components/scene-renderers/quiz-view.tsx']) {
    const path = join(NATIVE, name); hashes.push({ path: relative(ROOT, path), sha256: sha(await readFile(path)) });
  }
  const skills: Record<string, string> = {};
  for (const id of SKILL_IDS) {
    const path = join(NATIVE, 'skills/agent-runtime', id, 'SKILL.md');
    const source = await readFile(path); skills[id] = source.toString('utf8');
    hashes.push({ path: relative(ROOT, path), sha256: sha(source) });
  }
  const documentedRule = join(ROOT, 'docs/learning/low-reading-interaction-rule.md');
  const rulePath = await exists(documentedRule) ? documentedRule : join(ROOT, 'backend/content/low_reading_policy.v1.json');
  skills['low-reading'] = await readFile(rulePath, 'utf8');
  hashes.push({ path: relative(ROOT, rulePath), sha256: sha(skills['low-reading']) });
  hashes.push({ path: relative(ROOT, fileURLToPath(import.meta.url)), sha256: sha(await readFile(fileURLToPath(import.meta.url))) });
  const assets: Json[] = [];
  const teacherAssets = spec.teacherAvatar?.localPath ? [spec.teacherAvatar] : Object.values(spec.teacherAvatar ?? {});
  for (const media of [...(spec.sharedMedia ?? []), ...teacherAssets] as Json[]) {
    if (typeof media.localPath !== 'string' || typeof media.sha256 !== 'string') throw new Error('media_file_and_hash_required');
    const path = await realpath(resolve(ROOT, media.localPath));
    const localSrc = typeof media.src === 'string' && ((media.src.startsWith('/') && !media.src.startsWith('//')) || /^http:\/\/localhost:3000\/(?:textbooks|teachers)\/[A-Za-z0-9_./-]+$/.test(media.src));
    if (!within(ROOT, path) || !localSrc) throw new Error('media_out_of_scope');
    const content = await readFile(path); const digest = sha(content);
    if (digest !== media.sha256) throw new Error('media_hash_mismatch');
    assets.push({ id: media.id ?? null, src: media.src, path: relative(ROOT, path), sha256: digest, bytes: content.length });
  }
  const manifest = {
    schemaVersion: 'mira.course-generator-evaluation.v1', specSha256: sha(bytes), sources: hashes, assets,
    candidates, endpoint: ENDPOINT, parameters: { temperature: 0.6, thinking: { type: 'disabled' }, max_tokens: MAX_OUTPUT_TOKENS },
    limits: { courses: 2, models: candidates.length, pagesPerCourse: 8, calls: 34 * candidates.length, messagesUtf8Bytes: MAX_INPUT_BYTES, reservedPeakUsd: MAX_USD },
    scope: { nativePlannerContentActionsAssembly: true, outerAgent: false, webSearch: false, imageGeneration: false, videoGeneration: false, audio: false, publication: false, studentEvidence: false },
    spec,
  };
  return { manifest: { ...manifest, manifestSha256: sha(canonical(manifest)) }, spec, skills };
}
function skillContext(skills: Record<string, string>, phase: Phase, sceneType?: string): string {
  const blocks = ['Mira isolated core-generation evaluation. Do not announce publication, learner scores or mastery.', skills['low-reading']];
  if (phase === 'plan') blocks.push(section(skills['mira-primary-courseware'], 'Learning arc'), section(skills['k12-core-literacy-planning'], 'Settle the learning contract'));
  else {
    blocks.push(section(skills['mira-primary-courseware'], phase === 'actions' ? 'Narration and focus' : 'Page craft'));
    blocks.push(section(skills['k12-core-literacy-planning'], 'Universal non-negotiables'));
    if (sceneType === 'slide' && phase === 'content') blocks.push(skills['slide-craft'].replace(/^---[\s\S]*?---\s*/, ''));
    if (sceneType === 'interactive') blocks.push(section(skills['deep-interactive'], 'Choosing a widget type'), section(skills['deep-interactive'], 'keyPoints'));
    blocks.push(section(skills['learning-to-learn'], '两条内容红线'));
  }
  blocks.push('Evaluation constraint: 6–8 pages, only slide/quiz/interactive, meaningful pictured choices and manipulation, no PBL, external scripts or newly generated media. Teacher narration is text actions; no speechSynthesis. Return only the native requested output format.');
  return blocks.filter(Boolean).join('\n\n');
}
export function parseStrictJson(text: string): any {
  const cleaned = text.trim().replace(/^```(?:json)?\s*\n?/i, '').replace(/\n?\s*```\s*$/i, '');
  return JSON.parse(cleaned);
}
export function validateRaw(text: string, phase: Phase, sceneType?: string): void {
  if (phase === 'content' && sceneType === 'interactive') {
    const cleaned = text.trim().replace(/^```(?:html)?\s*\n?/i, '').replace(/\n?\s*```\s*$/i, '');
    if (!/<(?:html|div|body|main|section)\b/i.test(cleaned)) throw new Error('interactive_html_missing');
    return;
  }
  const parsed = parseStrictJson(text);
  if (phase === 'plan') {
    if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.outlines) || parsed.outlines.length < 6 || parsed.outlines.length > 8) throw new Error('plan_page_count_invalid');
    const types = new Set(parsed.outlines.map((o: Json) => o.type));
    if (![...TYPES].every(t => types.has(t))) throw new Error('plan_required_scene_type_missing');
    for (const o of parsed.outlines) {
      if (!TYPES.has(o.type) || typeof o.title !== 'string' || !o.title.trim() || typeof o.description !== 'string' || !o.description.trim()) throw new Error('plan_scene_invalid');
      if (o.type === 'interactive' && (!WIDGETS.has(o.widgetType) || !o.widgetOutline)) throw new Error('plan_widget_invalid');
      if (o.mediaGenerations?.length || o.pblConfig) throw new Error('plan_unsupported_generation');
    }
  } else if (phase === 'actions') {
    if (!Array.isArray(parsed) || !parsed.some(i => i?.type === 'text' && typeof i.content === 'string' && i.content.trim())) throw new Error('native_speech_actions_missing');
  } else if (sceneType === 'slide') {
    if (!parsed || !Array.isArray(parsed.elements) || !parsed.elements.length) throw new Error('slide_elements_missing');
  } else if (sceneType === 'quiz') {
    if (!Array.isArray(parsed) || !parsed.length || parsed.length > 8) throw new Error('quiz_questions_missing');
  } else throw new Error('unsupported_response_phase');
}
export class PaidStopped extends Error {}
export class PaidRunner {
  calls = 0; reserveUsd = 0; stopped = false;
  constructor(public output: string, private key: string, private fetcher: Fetcher = fetch, public progress: (row: Json) => void = () => {}) {}
  async ready(): Promise<void> {
    if (await exists(join(this.output, 'dispatch.ndjson'))) throw new Error('existing_dispatches_cannot_be_replayed');
  }
  async call(candidate: Candidate, identity: Json, messages: Json[]): Promise<string> {
    if (this.stopped) throw new PaidStopped('unknown_provider_outcome_stops_all_dispatch');
    const bytes = inputBytes(messages); const reserve = reservedUsd(candidate, bytes);
    if (bytes > MAX_INPUT_BYTES) throw new Error('request_messages_exceed_80000_utf8_bytes');
    if (this.calls >= MAX_CALLS || this.reserveUsd + reserve > MAX_USD) throw new Error('evaluation_budget_exhausted');
    const body = { model: candidate.model, messages, temperature: 0.6, thinking: { type: 'disabled' }, max_tokens: MAX_OUTPUT_TOKENS, stream: false };
    const requestId = sha(canonical({ ...identity, model: candidate.model, body }));
    const receiptPath = join(this.output, requestId + '.receipt.json');
    if (await exists(receiptPath)) throw new Error('existing_receipt_cannot_be_replayed');
    await save(join(this.output, requestId + '.request.json'), { requestId, ...identity, candidate: candidate.id, body, inputBytes: bytes, maximumReservedUsd: reserve });
    await append(join(this.output, 'dispatch.ndjson'), { requestId, ...identity, candidate: candidate.id, status: 'dispatched', maximumReservedUsd: reserve, time: new Date().toISOString() });
    this.calls += 1; this.reserveUsd += reserve;
    this.progress({ event: 'dispatch', candidate: candidate.id, ...identity, calls: this.calls, maximumReservedUsd: Number(this.reserveUsd.toFixed(6)) });
    const started = performance.now(); let response: Response; let raw: string;
    try {
      response = await this.fetcher(ENDPOINT, { method: 'POST', headers: { 'content-type': 'application/json', authorization: 'Bearer ' + this.key }, body: JSON.stringify(body), signal: AbortSignal.timeout(300_000), redirect: 'error' });
      raw = await response.text();
      // Durable provider receipt precedes every JSON or native-parser operation.
      await save(receiptPath, { requestId, ...identity, candidate: candidate.id, httpStatus: response.status, elapsedMs: Math.round(performance.now() - started), rawBody: raw });
    } catch {
      this.stopped = true;
      await append(join(this.output, 'dispatch.ndjson'), { requestId, status: 'unknown', time: new Date().toISOString() });
      throw new PaidStopped('provider_outcome_unknown_no_automatic_retry');
    }
    if (!response.ok) {
      const unknown = response.status === 408 || response.status >= 500;
      this.stopped ||= unknown;
      await append(join(this.output, 'dispatch.ndjson'), { requestId, status: unknown ? 'unknown' : 'rejected', httpStatus: response.status });
      throw unknown ? new PaidStopped('provider_outcome_unknown_no_automatic_retry') : new Error('provider_rejected_' + response.status);
    }
    await append(join(this.output, 'dispatch.ndjson'), { requestId, status: 'received', time: new Date().toISOString() });
    const parsed = JSON.parse(raw); const choice = parsed.choices?.[0];
    await save(join(this.output, requestId + '.usage.json'), { requestId, usage: parsed.usage ?? null, responseModel: parsed.model ?? null, finishReason: choice?.finish_reason ?? null });
    if (choice?.finish_reason !== 'stop' || typeof choice.message?.content !== 'string' || !choice.message.content.trim()) throw new Error('provider_reply_incomplete');
    return choice.message.content;
  }
}
async function readKey(): Promise<string> {
  const text = await readFile(join(ROOT, 'openmaic-runtime/.env'), 'utf8');
  const matches = text.split(/\r?\n/).filter(line => /^\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=/.test(line));
  if (matches.length !== 1) throw new Error('one_runtime_deepseek_key_required');
  let value = matches[0].replace(/^\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=\s*/, '').trim();
  try {
    if (value.startsWith('"')) value = JSON.parse(value); else if (value.startsWith("'")) value = value.slice(1, value.lastIndexOf("'")); else value = value.replace(/\s+#.*$/, '');
  } catch { throw new Error('runtime_deepseek_key_invalid'); }
  if (!value || /\s/.test(value)) throw new Error('runtime_deepseek_key_invalid');
  return value;
}
function mediaInputs(spec: Json, course: Json) {
  const selected = (spec.sharedMedia ?? []).filter((m: Json) => !course.sharedMediaIds || course.sharedMediaIds.includes(m.id));
  const images = selected.map((m: Json, i: number) => ({ id: m.id ?? 'img_' + (i + 1), src: m.src, description: m.description ?? '', pageNumber: i + 1, ...(m.width ? { width: m.width } : {}), ...(m.height ? { height: m.height } : {}) }));
  return { images, mapping: Object.fromEntries(images.map((m: Json) => [m.id, m.src])) };
}
export async function prepare(specPath: string, output: string, candidates: readonly Candidate[] = CANDIDATES): Promise<Awaited<ReturnType<typeof freeze>>> {
  output = resolve(output);
  if (!within(OUTPUT_ROOT, output)) throw new Error('output_must_be_private_course_evals_child');
  await mkdir(output, { recursive: true, mode: 0o700 }); await chmod(output, 0o700);
  const resolvedOutput = await realpath(output);
  if (!within(await realpath(OUTPUT_ROOT), resolvedOutput)) throw new Error('output_symlink_out_of_scope');
  const frozen = await freeze(specPath, candidates); const manifestPath = join(output, 'manifest.json');
  if (await exists(manifestPath)) {
    const existing = JSON.parse(await readFile(manifestPath, 'utf8'));
    if (existing.manifestSha256 !== frozen.manifest.manifestSha256) throw new Error('frozen_evaluation_scope_changed');
  } else await save(manifestPath, frozen.manifest);
  return frozen;
}
async function execute(frozen: Awaited<ReturnType<typeof freeze>>, output: string): Promise<void> {
  const generation = await import(pathToFileURL(join(NATIVE, 'packages/@openmaic/generation/dist/index.js')).href);
  const runner = new PaidRunner(output, await readKey(), fetch, row => process.stdout.write(JSON.stringify(row) + '\n'));
  await runner.ready(); const summaries: Json[] = [];
  const agents = [{ id: 'teacher', name: '小语老师', role: 'teacher', persona: '用短句和具体图片，引导孩子自己操作和解释。' },
    ...['小禾', '小米', '小宇', '小朵'].map((name, i) => ({ id: 'peer-' + (i + 1), name, role: 'student', persona: '小学同伴，提出短问题。' }))];
  for (const course of frozen.spec.courses) for (const candidate of frozen.manifest.candidates as Candidate[]) {
    if (runner.stopped) break;
    const media = mediaInputs(frozen.spec, course);
    const lane = candidate.id + '-' + course.id; const stageId = 'om_eval_' + sha(frozen.manifest.manifestSha256 + lane).slice(0, 24);
    const scenes: Json[] = []; let phase: Phase = 'plan'; let page = 0; let sceneType: string | undefined;
    const aiCall = async (system: string, user: string, images?: any[]): Promise<string> => {
      if (images?.length) throw new Error('vision_inputs_not_authorized_for_pro_parity');
      const identity = { courseId: course.id, phase, page };
      const mediaText = media.images.length ? '\n\nAlready verified original teaching assets, unchanged for both models. Use exact src or assigned image IDs; never invent image URLs:\n' + JSON.stringify(media.images) : '';
      if (runner.calls >= frozen.manifest.limits.calls) throw new Error('evaluation_candidate_call_limit');
      const contractText = course.learningContract ? generation.learningSceneInstructions(course.learningContract) : '';
      const text = await runner.call(candidate, identity, [{ role: 'system', content: system + '\n\n' + skillContext(frozen.skills, phase, sceneType) + contractText }, { role: 'user', content: user + mediaText }]);
      validateRaw(text, phase, sceneType); return text;
    };
    try {
      const planned = await generation.generateSceneOutlinesFromRequirements(course.requirements, undefined, media.images, aiCall, { imageGenerationEnabled: false, videoGenerationEnabled: false, visionEnabled: false, imageMapping: media.mapping });
      if (runner.stopped) throw new PaidStopped('provider_outcome_unknown_no_automatic_retry');
      if (!planned.success || !planned.data) throw new Error('native_planning_failed');
      const outlines = planned.data.outlines;
      if (outlines.length < 6 || outlines.length > 8 || outlines.some((o: Json) => !TYPES.has(o.type))) throw new Error('native_plan_invalid');
      await save(join(output, lane + '.plan.json'), planned.data);
      for (const [index, outline] of outlines.entries()) {
        page = index + 1; sceneType = outline.type; phase = 'content';
        // Neither model receives the other model's prior pages or model replies.
        const content = await generation.generateSceneContent(outline, aiCall, { agents, languageDirective: planned.data.languageDirective,
          assignedImages: media.images, imageMapping: media.mapping, visionEnabled: false, interactiveIncludeKatex: false,
          explorationGame: outline.widgetType === 'game', allowProceduralSkill: false,
          ...(course.learningContract ? { learningContract: course.learningContract } : {}) });
        if (!content) throw new Error('native_content_failed');
        if (course.learningContract && outline.type === 'interactive') {
          for (const script of generation.interactiveScripts(content.html)) {
            try { new Script(script); } catch { throw new Error('LEARNING_SCENE_SCRIPT_SYNTAX_INVALID'); }
          }
        }
        phase = 'actions';
        const actions = await generation.generateSceneActions(outline, content, aiCall, { agents, languageDirective: planned.data.languageDirective,
          ctx: { pageIndex: page, totalPages: outlines.length, allTitles: outlines.map((o: Json) => o.title), previousSpeeches: (scenes.at(-1)?.actions ?? []).filter((a: Json) => a.type === 'speech').map((a: Json) => a.text).slice(-3) } });
        if (!actions.length || !actions.some((a: Json) => a.type === 'speech' && a.text?.trim())) throw new Error('native_actions_failed');
        if (course.learningContract) {
          for (const action of actions) if (action.type === 'speech') generation.assertNoInventedMastery(action.text, course.learningContract);
          if (outline.type === 'slide') generation.assertNoInventedMastery(JSON.stringify(content.elements), course.learningContract);
        }
        const scene = generation.buildCompleteScene(outline, content, actions, stageId, { sceneId: stageId + '_p' + page });
        if (!scene) throw new Error('native_scene_assembly_failed');
        scenes.push(scene); await save(join(output, lane + '.partial-scenes.json'), scenes);
        runner.progress({ event: 'page_saved', candidate: candidate.id, courseId: course.id, page, type: sceneType });
      }
      const now = Date.now(); const stage = { id: stageId, name: planned.data.courseTitle || course.title, languageDirective: planned.data.languageDirective,
        style: 'interactive', createdAt: now, updatedAt: now, generatedAgentConfigs: agents.map((a, i) => ({ ...a, avatar: i === 0 ? frozen.spec.teacherAvatar?.[course.subject]?.src ?? frozen.spec.teacherAvatar?.src ?? '/avatars/student1.svg' : '/avatars/student' + (((i - 1) % 3) + 1) + '.svg', color: ['#47684e', '#a97937', '#6c83a1', '#bd897c', '#847f9b'][i], priority: i === 0 ? 10 : 5 })) };
      await save(join(output, lane + '.classroom.json'), { id: stageId, stage, scenes, createdAt: new Date().toISOString() });
      summaries.push({ courseId: course.id, candidate: candidate.id, status: 'native_draft_generated', stageId, pages: scenes.length, classroomFile: lane + '.classroom.json', audioGenerated: false, publicationAllowed: false });
    } catch (error: any) {
      summaries.push({ courseId: course.id, candidate: candidate.id, status: runner.stopped ? 'stopped_unknown' : 'failed', phase, page, pagesSaved: scenes.length, errorCode: error instanceof PaidStopped ? error.message : String(error?.message ?? 'evaluation_failed').slice(0, 120) });
    }
    await save(join(output, 'summary.json'), { schemaVersion: 'mira.course-generator-evaluation-result.v1', manifestSha256: frozen.manifest.manifestSha256, callsDispatched: runner.calls, maximumReservedUsd: runner.reserveUsd, stoppedForUnknown: runner.stopped, results: summaries, productionConfigurationChanged: false });
  }
  runner.progress({ event: 'evaluation_ended', callsDispatched: runner.calls, maximumReservedUsd: Number(runner.reserveUsd.toFixed(6)), stoppedForUnknown: runner.stopped });
}
export async function main(argv = process.argv.slice(2)): Promise<void> {
  let specPath = join(ROOT, 'backend/content/evals/course_generator_comparison.v1.json'); let output = ''; let paid = false; let candidateId = 'both';
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--spec') specPath = resolve(argv[++i]); else if (argv[i] === '--output') output = resolve(argv[++i]);
    else if (argv[i] === '--candidate') candidateId = argv[++i];
    else if (argv[i] === '--execute-paid-comparison') paid = true; else throw new Error('unknown_argument');
  }
  if (!output) throw new Error('output_required');
  if (Number(process.versions.node.split('.')[0]) !== 24) throw new Error('node_24_required');
  if (!['both', 'pro', 'flash'].includes(candidateId)) throw new Error('invalid_candidate');
  const candidates = candidateId === 'both' ? CANDIDATES : CANDIDATES.filter(candidate => candidate.id === candidateId);
  const frozen = await prepare(specPath, output, candidates);
  process.stdout.write(JSON.stringify({ event: 'prepared', manifestSha256: frozen.manifest.manifestSha256, courses: frozen.spec.courses.map((c: Json) => c.id), maxCalls: MAX_CALLS, maximumUsd: MAX_USD, providerDispatched: false }) + '\n');
  if (paid) await execute(frozen, output);
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(error => { process.stderr.write(JSON.stringify({ error: String(error?.message ?? 'evaluation_failed').slice(0, 120) }) + '\n'); process.exitCode = 1; });
