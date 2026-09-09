# Formal Content Authority Redesign

## Status

Approved under the existing Scheme A production-flow authority on 2026-08-24.
This redesign resolves the Task-4 and Task-6 five-round breakers. It changes no
database schema, public API, paid Provider policy, Runtime publication rule or
historical data.

## Problem

The previous Grade-1 formal validators attempted to infer two bounded language
contracts with substring searches:

1. tens-and-ones expressions were found by restarting a regex near `个十`, so
   malformed numeric syntax could be skipped or partially accepted;
2. simple Chinese sentences treated arbitrary Han text as a subject or identity
   complement, so grammatical markers could be swallowed into a noun and valid
   marker-bearing nouns could be rejected.

Repeated local fixes proved the patterns themselves unsound. The replacement
must make ambiguity explicit and fail closed before a paid dispatch or a formal
Host receipt.

## Authority A: Number-Sense Unit-Phrase Lexer

### Interface

Node exports a pure classifier:

```text
classifyNumberSenseUnitPhrases(text) ->
  { status: "not-representation" | "valid" | "malformed", representations: [...] }
```

Python exposes the same behavior through its Task-5 preflight. Both runtimes
normalize input with NFKC and Python-compatible whitespace semantics. A fixed
literal cross-runtime corpus proves parity; neither runtime derives expected
answers from the other.

### Complete grammar

The lexer recognizes only these formal forms:

```text
tens-only := UINT WS? "个十"
pair      := UINT WS? "个十" WS? "和" WS? UINT WS? "个一"
placeholder := "几个十" WS? "和" WS? "几个一"
```

`UINT` is canonical ASCII `0|[1-9][0-9]*`. `WS` is the exact
Python-compatible whitespace set already frozen by Task 4.

- `valid`: a fully consumed `tens-only` or `pair` whose values satisfy the
  sealed 0–20 place-value authority: tens 0 or 1 with ones 0–9, or tens 2 with
  ones 0.
- `not-representation`: no unit phrase, the exact pedagogical placeholder, or
  a standalone `UINT个一` that is outside this pair authority.
- `malformed`: a `个十` unit with a missing/invalid tens token; a pair with a
  missing/wrong connector, token or unit; any sign, decimal, exponent, radix,
  underscore, repeated operator, Unicode operator, numeric continuation after
  `个一`, or mixed placeholder/numeric pair.

The scanner must consume an entire unit phrase. It may use surrounding Han text
as a boundary (`18由1个十和8个一组成。`) but must never restart at a digit inside
an invalid numeric token. Multiple phrases are all checked; one malformed
phrase makes the containing artifact malformed.

### Integration

Task 4 calls the classifier for every string nested in a number-sense request
or generated checkpoint and rejects `malformed` before returning an accepted
checkpoint. Task 5 performs the same classification before ledger reservation;
Node rejection after a Python pass is a parity defect and creates zero ledger
and zero process evidence.

## Authority B: Sealed Grade-1 Sentence Word Boundaries

### Dataset amendment

The Task-1 `chinese.simple_sentence_punctuation.v1` inventory advances its
predicate grammar version and adds two bounded lists:

```text
markerBearingSubjectNouns
identityComplements
```

The initial sealed subject-noun set contains the reviewed ambiguous Grade-1
nouns `太空人`, `真菌`, `过山车`, `太太`, and `老太太`. The identity-complement
set contains only approved Grade-1 identity nouns used by the formal generator,
including `老师`, `学生`, `同学`, `朋友`, `医生`, `工人`, `农民`, `警察`, close
family roles, `孩子`, and `太空人`.

Both lists are exact, unique, bounded Han strings, included in the canonical
dataset hash, boundary version, target fingerprint and generator-facing allowed
content. No validator-local exception list is permitted.

### Exact parser

The Host parser accepts a sentence body only when one complete sealed production
matches:

```text
subject + sealed bare predicate
subject + sealed bare predicate + sealed aspect marker
subject + sealed identity marker + sealed identity complement
subject + sealed description marker + sealed state predicate
```

A subject is non-empty Han text, cannot end in `的/地/得`, and may contain an
aspect/identity/description marker only when the entire subject is an exact
`markerBearingSubjectNouns` member. Identity complements must be exact
`identityComplements`; description complements must be exact `statePredicates`.
No production may fall back after partially consuming a marker.

This intentionally rejects unsealed or ambiguous sentences instead of trying
to implement general Chinese parsing. The generation prompt receives the same
finite authority, so formal courses are generated inside the accepted domain.

## Evidence and Error Semantics

- Task-4 malformed unit phrases fail before Provider-result acceptance.
- Task-5 parity failures create zero reservation/process; an already-dispatched
  unusable result follows the existing canonical ambiguous-result policy.
- Task-6 grammar mismatches are deterministic content rejections only after all
  control/provenance evidence passes.
- Dataset or fingerprint drift is a control error, never a content rejection.
- No raw Provider text, secret, dynamic issue text or parser trace is persisted.

## Required Tests

1. Literal Node lexer corpus covering all 222 reviewer cases plus valid controls.
2. Python mirror corpus with exact Node parity for every case.
3. Nested phase 3/6/11/14 checkpoints: malformed means zero accepted output;
   Python preflight means zero ledger/process.
4. Task-1 mutation tests for missing/extra/duplicate/non-Han subject and identity
   inventories, canonical dataset pin, boundary version and target fingerprint.
5. Full Host receipt tests for all previous marker bypasses and legal controls,
   including `太太工作。`, `老太太工作。`, `妈妈是太空人。`.
6. Negative identity complements such as `我是了工作。`, `妈妈是很跑步。`,
   `妈妈是过学习。`, and `妈妈是真学习。`.
7. Existing Task-1 through Task-6 regression suites remain green; no DB,
   Provider, Runtime, media or publication call is part of this redesign.

## Scope Boundary

This is a deterministic Grade-1 formal-content contract, not a general-purpose
Chinese or mathematical-language parser. Future vocabulary expansion changes
the versioned dataset explicitly and re-runs the same downstream fingerprint
and receipt gates.
