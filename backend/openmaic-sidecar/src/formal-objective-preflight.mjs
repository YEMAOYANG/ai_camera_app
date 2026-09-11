import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {ContractError} from './contract.mjs';

// Runtime interpreter comes from the Python adapter, never from model input.
// This is the same pure Host evaluator used at final publication, not a second
// JavaScript copy of the grade/difficulty rules.
export function formalObjectiveQuestionIssues(request, candidate) {
  if (!/^primary_[2-6]$/.test(request.gradeCode)) return [];
  const python = process.env.OPENMAIC_HOST_VALIDATOR_PYTHON;
  if (!python || !python.startsWith('/')) {
    throw new ContractError('Host objective validator unavailable', 'question_phase_preflight_rejected');
  }
  const result = spawnSync(python, ['-B', fileURLToPath(new URL('../../content/formal_question_preflight_cli.py', import.meta.url))], {
    input: JSON.stringify({gradeCode: request.gradeCode, subject: request.subject,
      skillId: request.skillBoundary.skillId, objectivePolicy: request.objectivePolicy,
      questions: candidate?.questions}),
    encoding: 'utf8', timeout: 10000, maxBuffer: 65536,
    env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'},
  });
  let output;
  try { output = JSON.parse(result.stdout); } catch { /* Fail before any paid repair. */ }
  if (result.error || result.status !== 0 || !output
    || Object.keys(output).sort().join(',') !== 'issues,schemaVersion'
    || output.schemaVersion !== 'mira.formal-objective-preflight.v1'
    || !Array.isArray(output.issues) || output.issues.length > 5
    || output.issues.some(issue => !issue || Object.keys(issue).sort().join(',') !== 'question,reason'
      || !Number.isInteger(issue.question) || issue.question < 1 || issue.question > 5
      || typeof issue.reason !== 'string' || issue.reason.length > 240)) {
    throw new ContractError('Host objective validator unavailable', 'question_phase_preflight_rejected');
  }
  return output.issues;
}

export function assertFormalObjectiveCandidate(request, candidate) {
  const issues = formalObjectiveQuestionIssues(request, candidate);
  if (issues.length) {
    throw new ContractError(`Host objective rules: ${issues.map(x => `q${x.question}: ${x.reason}`).join('; ')}`, 'invalid_generation');
  }
  return candidate;
}
