# Personal AI Companion — Unified Architecture Specification v3
## (Memory System + Conversational Cognition Layer)

**Purpose of this document:** Complete build spec for an AI coding agent to implement this system end-to-end. This is a merge of two prior specs — the memory/vault architecture (v2) and the conversational cognition proposal — into one coherent system. They are not two features bolted together: the cognition layer is what the orchestrator's "classify → retrieve → respond" loop was always a simplified stand-in for, and the vault/memory system is what gives the cognition layer's Person Model and layered memory somewhere real to live. Follow the phases in order.

**What changed in this merge, and why (read this before building):** The two source documents agree almost everywhere but conflict in three places, resolved as follows:

1. **Retrieval philosophy.** The memory spec ranks by similarity + recency. The cognition spec wants retrieval ranked by "would this memory change my response" — a full `argmax P(M changes response)` is not cheaply computable per-candidate without an LLM call per chunk, which would violate the "retrieve the smallest relevant set, don't context-stuff" principle both documents actually share. **Resolution:** decision-relevance is approximated, not computed exactly, by using the structured output of the Interpreter (needs, topic, entities) as a metadata boost layered on top of the existing similarity+recency re-rank, not a replacement for it. A true learned relevance model is a named "later" item (§14), not a v1 blocker.
2. **Two classification axes.** The memory spec's "mode" (checkin/confide/project/recall/mixed) governs *what to retrieve and where to save*. The cognition spec's "action" (ANSWER/ASK/REFLECT/etc.) governs *what conversational move the reply makes*. These are orthogonal, both kept, and computed in the same two model calls per turn the system already needed — no extra latency or cost added by merging them (§7, §9).
3. **Safety boundary vs. richer inference.** The cognition layer infers a lot about emotional state and implicit intent. That inference must never be allowed to silently promote a conversation into `confide` mode (and therefore into the secrets-tier database) on its own — entering `confide` still requires an explicit user signal or a confirm step, exactly as fixed in v2 §4 of the retrieval design. A richer model of the person is not a looser privacy gate.

---

## 1. What This System Is

A private, local-first personal companion that:
- Holds ongoing conversation with the user (text, later voice)
- Explicitly models, at every turn, what the person is communicating, what they need, what's known about them that's relevant right now, and what conversational action is appropriate — before generating language
- Extracts and stores structured, layered memory: working, episodic, semantic, relational, and procedural
- Retrieves relevant past context intelligently — not by similarity alone, but weighted toward what would actually change the response
- Stores everything as human-readable Markdown in an Obsidian vault the user fully owns
- Tracks the user's projects/tasks alongside their emotional life, in the same system
- Builds an increasingly accurate model of the individual person, distinguishing observation from hypothesis from confirmed fact, and tests that model against what actually happens
- Never loses long-term coherence, even after years of daily use

**What it is not:** a therapist, a clinician, a replacement for real human support, or a system that should ever claim confidentiality guarantees it can't back up legally. It is also not a system whose "genuineness" is measured by how human-like its sentences sound — genuineness here is operationally defined in §2.6 as accuracy and continuity of the person model, not surface fluency.

---

## 2. Core Design Principles

1. **Retrieval over context-stuffing.** Never dump the whole vault, or the whole person model, into the prompt. Retrieve the smallest relevant set. This applies to `/core/` and the Person Model exactly as it applies to chunk retrieval (§8.5).
2. **Plaintext is the source of truth.** All databases (vector index, prediction log, evaluation log) are *derived* from the Markdown vault. If deleted, a re-index must rebuild them fully.
3. **Privacy tiers are enforced by physical separation, not a query clause — and not by inference.** Secrets live in a separate database (§8.2). Entry into `confide` mode requires an explicit user signal, never an inferred emotional-intensity score alone, however sophisticated the Interpreter becomes.
4. **Human-in-the-loop for permanent memory and for promoting a hypothesis to a fact.** The system may *propose*; a human confirms before anything is written to `/core/` or a hypothesis's status changes to `fact` (§13).
5. **Every write is structurally guaranteed to be attributable and reversible — not just requested via prompt.** Memory writes and action/prediction logging both go through tool-calling with schema validation (§9.2, §10.2), never free-text parsing.
6. **Never let the model imply precision it doesn't have.** Frequency/pattern claims require a structured aggregate query result in context (§8.4). Preference claims about the person require a confidence score and evidence count, and must be phrased as conditional, not absolute, whenever evidence is mixed (§6.4).
7. **Separate the decision from the language.** The system should decide *what conversational move to make* before deciding *how to phrase it*. This split is architecturally real — a distinct tool call (§9) — not just a mental step folded silently into one text generation.
8. **The person is the training signal.** General conversational competence comes from the base model's population-level knowledge. Everything specific to *this* person — what they need in which situations, how they like to be talked to — is learned from interaction with them and stored in the Person Model, tested, and revised (§6, §10).

---

## 3. System Architecture

```
                              ┌───────────────┐
                              │     USER      │
                              └───────┬───────┘
                                      ▼
                         ┌────────────────────────┐
                         │  CONVERSATION INTERFACE  │
                         └────────────┬─────────────┘
                                      ▼
                    ┌──────────────────────────────────┐
                    │  CALL A — INTERPRETER (cheap/fast) │
                    │  • structured interpretation object  │
                    │  • compares against last turn's       │
                    │    logged prediction (prediction error) │
                    │  • proposes mode (retrieval routing)      │
                    └────────────┬───────────────────────────┘
                                 ▼
                 ┌───────────────────────────────┐
                 │      RETRIEVAL (two-stage,      │
                 │   mode + sensitivity gated)       │
                 │  Stage 1: vector candidates         │
                 │  Stage 2: re-rank by similarity +     │
                 │  recency + interpretation-boost         │
                 │  + structured + relational retrieval      │
                 └───────────┬─────────────────┬────────────┘
                             ▼                 ▼
                    ┌────────────────┐  ┌─────────────────┐
                    │  NORMAL INDEX    │  │  SECRETS INDEX    │
                    │  index.sqlite      │  │  secrets_index.  │
                    │  (episodic/semantic/ │  │  sqlite          │
                    │   relational/procedural)│  │  separate connection│
                    └────────────────┘  └─────────────────┘
                             │
                             ▼
                    ┌─────────────────────┐
                    │    PERSON MODEL       │  (budgeted load, §8.5)
                    │  beliefs / hypotheses / │
                    │  confirmed facts / style  │
                    └──────────┬──────────────┘
                               ▼
        ┌──────────────────────────────────────────────┐
        │  CALL B — MAIN MODEL (Claude API)               │
        │  Given: core memory + person model + retrieved    │
        │  chunks + aggregate data + interpretation +         │
        │  recent turns                                         │
        │  Emits THREE structured outputs in one call:            │
        │   1. select_action tool call (chosen action +             │
        │      predicted user reaction — logged for next turn)       │
        │   2. text reply to the user                                  │
        │   3. save_memory tool call (or explicit decline)               │
        └───────────┬─────────────────────┬─────────────────────────────┘
                    ▼                     ▼
              USER (reply)          WRITE-BACK
                    │                     │
                    ▼                     ▼
         ┌────────────────────┐  ┌──────────────────────┐
         │  predictions_log.jsonl│  │  VAULT (filesystem)    │
         │  (working-memory scale,│  │  source of truth,        │
         │   compared next turn)   │  │  episodic/semantic/       │
         └────────────────────┘  │  relational/procedural       │
                                 └──────────┬───────────────────┘
                                            ▼
                                 ┌─────────────────────┐
                                 │  RE-INDEX (async) +    │
                                 │  WEEKLY CONSOLIDATION    │
                                 │  (themes, hypothesis       │
                                 │  confidence updates)         │
                                 └─────────────────────┘
```

Two model calls per turn, same as a naive classifier+responder split would have needed — the richer schemas in §7 and §9 don't add a third call.

---

## 4. Vault Structure

The five memory layers from the cognition spec map onto the existing vault folders rather than requiring new ones — this keeps Principle 1 intact instead of multiplying storage locations.

| Cognition layer | Vault location | Notes |
|---|---|---|
| **Working memory** | Not persisted to the vault. Lives in `recent_turns` (last N messages) plus `/_meta/predictions_log.jsonl` (last logged prediction, current topic/goal). Cleared or rolled into episodic memory at session end. | Doc2 §9.1 — minutes-scale, not durable. |
| **Episodic memory** | `/daily/*.md`, `/projects/*/log.md` | Specific dated events. Already the append-only, section-metadata format from v2 §4.1. |
| **Semantic memory** | `/people/*.md` (general facts section), `/core/*.md` | General facts, not tied to a specific conversation. |
| **Relational memory** | `/themes/*.md`, plus cross-links via `people`/`projects` tags already in frontmatter | Connections between concepts, consolidated weekly (§11). |
| **Procedural / conversational memory** | `/people/*.md` (communication-style section), `/core/system-notes.md` (global default) | How to interact with this person specifically, vs. globally. |

```
/vault
  /daily/                       # episodic — unchanged from v2
  /people/
    sarah.md                     # semantic + procedural + hypotheses (§6.4 — new structure below)
  /projects/
    book-manuscript/
      overview.md
      log.md                      # episodic, project-scoped
      tasks.md
  /themes/                        # relational — AI-generated pattern notes
  /secrets/                        # isolated, own DB, own encryption key
  /core/                            # semantic + procedural, curated, budget-loaded
    values.md
    people-index.md
    recurring-patterns.md
    system-notes.md
    _proposed/
  /_meta/
    index.sqlite                     # episodic/semantic/relational/procedural chunks
    secrets_index.sqlite               # secrets chunks only, separate connection
    predictions_log.jsonl                # working-memory scale — see §10.2
    evaluation_log.jsonl                  # lightweight per-turn signals — see §14
    index_log.jsonl                        # audit trail
    dead_letter.jsonl                       # failed structured writes, for review
    file.locks/
```

### 4.1 Person-note structure — hypotheses need the same fix daily notes needed

A single `/people/sarah.md` file accumulates many independent hypotheses over months (`prefers detail`, `avoids small talk`, `gets anxious before family visits`), each with its own confidence and evidence count. Putting that in file-level frontmatter has the exact same problem v2 fixed for daily notes: one YAML block can't hold many independently-evolving records. Same fix, applied here: **file-level frontmatter for the note's identity, inline structured blocks per hypothesis in the body.**

```markdown
---
id: "sarah"
type: person
sensitivity: normal
source: user
---

## Communication Style
<!-- meta: {"status": "fact", "confidence": 1.0, "source": "ai-proposed", "confirmed": true} -->
Prefers conceptual explanations over step-by-step instructions. Wants
the "why" before the "how." Dislikes unnecessary simplification.

## Hypothesis: prefers brevity under high urgency
<!-- meta: {"status": "hypothesis", "confidence": 0.71, "evidence_count": 4,
     "last_confirmed": null, "contradicts": null,
     "evidence": ["2026-08-02", "2026-08-19", "2026-09-10", "2026-09-24"]} -->
Detailed explanations are generally preferred, but on four occasions
under explicit time pressure the user asked for the short version
directly. Holding as conditional: detail by default, brevity when
urgency is signaled.

## Fact: has ridden horses for several years
<!-- meta: {"status": "fact", "confidence": 1.0, "source": "user", "confirmed": true} -->
Stated directly, multiple times, not inferred.
```

`status` is one of `observation | hypothesis | fact`. Only a human accept in the curation flow (§13) can move a `hypothesis` to `fact` with `confirmed: true` — the system can raise confidence indefinitely through evidence accumulation but cannot self-promote to `fact` (Principle 4). The indexer (§8.1) parses this the same way it parses daily-note sections — one chunk per block, metadata from that block's inline comment, not the file header.

---

## 5. Conversation Interpretation (Call A)

Every incoming message is interpreted before anything else happens. This is a cheap/fast model call (or, for early phases, a heuristic — see Phase 1), not the main Claude call.

```json
{
  "literal_content": "...",
  "topic": "...",
  "entities": { "people": ["mother"], "projects": [] },
  "intent": "...",
  "implicit_intent": "...",
  "emotional_state": "...",
  "needs": ["acknowledgment", "clarification"],
  "urgency": 0.0,
  "certainty": 0.0,
  "mode_suggestion": "checkin | confide | project | recall | mixed",
  "mode_requires_confirmation": true,
  "prediction_check": {
    "had_prior_prediction": true,
    "prior_predicted_action": "REFLECT",
    "prior_predicted_reaction": "user would continue exploring the topic",
    "actual_reaction_category": "topic_changed | continued | clarification_requested | explicit_feedback | confirmed",
    "prediction_error": "none | low | moderate | high"
  }
}
```

**`mode_suggestion` is advisory only for `confide`.** If the message content looks like a disclosure but the user hasn't explicitly signaled they want it held privately/separately, `mode_suggestion` stays `mixed` or `checkin` and `mode_requires_confirmation: true` is set — the orchestrator then either asks directly ("Do you want me to hold onto that just for you, separately?") or defaults to normal-tier storage with a note that it can be moved to secrets if the user asks. This is the concrete mechanism for Principle 3: inference can *suggest*, never *promote into*, the secrets tier.

`prediction_check` is how the closed learning loop (§10) actually closes — it's computed here, at the start of the *next* turn, by comparing this message against whatever was logged in `predictions_log.jsonl` at the end of the previous turn.

---

## 6. The Person Model

### 6.1 What it holds

```
PERSON
├── What they know / don't know
├── What they care about
├── What they're trying to accomplish (current goals)
├── What they've experienced (pointer into episodic memory, not duplicated)
├── How they communicate (procedural — §4.1)
├── How they react
├── What they value, avoid, repeatedly return to
├── Important relationships
├── Current projects
└── Status of every belief above: observation | hypothesis | fact
```

### 6.2 Population knowledge vs. individual knowledge

The base Claude model already carries population-level conversational competence (people often communicate indirectly, a question can be an invitation rather than a request for facts, etc.) — this is not something the system needs to build. What the system builds is exclusively the **individual** layer on top: this specific person's patterns, loaded per-turn from `/people/{name}.md` and `/core/`, subject to the token budget in §8.5. The system prompt (§9.1) explicitly frames retrieved person-model content as *additional to*, not a replacement for, the model's general conversational judgment.

### 6.3 Observation → hypothesis → fact

Every inferred property carries this status explicitly (§4.1's `status` field), never silently collapses to a flat fact:

- **Observation** — something the person did/said, once, logged with no interpretation attached yet.
- **Hypothesis** — a pattern proposed across multiple observations, carrying `confidence` and `evidence_count`, always phrased as conditional when evidence is mixed (Principle 6).
- **Fact** — either stated directly by the user, or a hypothesis a human has explicitly confirmed via the curation flow (§13). Never self-promoted.

### 6.4 Testing the model — the prediction loop, concretely

This is the mechanism, not just the idea:

1. At the end of Call B, `select_action`'s output includes `predicted_user_reaction` — a short, specific, falsifiable prediction ("I expect the user to keep exploring this topic rather than ask a factual follow-up").
2. This is written to `predictions_log.jsonl`, keyed to the conversation, with the hypothesis/hypotheses (if any) it was based on.
3. At the start of the *next* turn, Call A's `prediction_check` (§5) compares what actually happened against the logged prediction and assigns `prediction_error`.
4. `prediction_error` is not acted on turn-by-turn (too noisy, too expensive to update confidence on every single message) — it accumulates in `predictions_log.jsonl` and is consumed by the weekly consolidation job (§11), which updates the relevant hypothesis's `confidence` and `evidence_count` in the person note in one batch, the same way theme summarization already works. A single high-error turn should not swing a confidence score; a consistent pattern of errors across a week should.

---

## 7. Retrieval Layer

### 7.1 Multiple retrieval mechanisms, not vector-only

```
Memory = Vector (semantic similarity) + Structured (SQL/metadata) + Relational (tag-graph traversal)
```

- **Semantic** — embedding similarity, as in v2.
- **Structured** — direct SQL filters on frontmatter/inline-metadata fields (mood, tags, project, date range). This is what powers the aggregate-frequency queries in §7.3 and answers "what do I know about X" without a fuzzy similarity search.
- **Relational** — SQL JOINs across the `people`/`projects`/`tags` arrays already stored per chunk, plus `/themes/*.md` (which *is* consolidated relational memory). A full graph database is not needed for v1-scale vaults; this is a named later-upgrade item (§14) if the tag-graph approach stops scaling.

### 7.2 Two-stage retrieval, now with an interpretation-informed boost

The v2 formula (similarity + recency, mode-weighted alpha) is extended with a third term approximating decision-relevance, rather than replaced:

```
function retrieve(query, interpretation, k=8):
  1. Determine target DB from interpretation.mode_suggestion (never 'confide'
     unless the user explicitly confirmed it — see §5); secrets DB connection
     is never opened on any other path.
  2. Embed the query. Stage 1: cosine similarity, top N=40 candidates,
     filtered to the current embedding_model/version (v2 §8.1).
  3. Stage 2 — re-rank:
     recency_weight   = exp(-ln(2) * days_since(chunk.date) / 30)
     relevance_boost  = 1.0 if chunk.tags/people/projects overlap with
                         interpretation.entities or interpretation.needs,
                         else 0.0   (cheap, structural — this is the v1
                         approximation of "would this change my response,"
                         not a learned model — see §14)
     alpha, beta = mode_weights[interpretation.mode_suggestion]  (table below)
     combined = alpha * normalized_similarity
              + beta  * recency_weight
              + (1 - alpha - beta) * relevance_boost
     sort by combined, take top k
  4. If interpretation carries a frequency/pattern cue, also run the
     structured aggregate query (§7.3) and attach its result separately.
  5. Fetch /core/ and the relevant Person Model sections, budget-limited (§8.5).
  6. Return { core_memory, person_model, retrieved_chunks, aggregate_data }
```

| mode | alpha (similarity) | beta (recency) | rationale |
|---|---|---|---|
| `recall` | 0.7 | 0.1 | relevance dominates; the entity/topic overlap boost does most of the disambiguation work here |
| `checkin` | 0.4 | 0.4 | recent state matters as much as topical similarity |
| `project` | 0.5 | 0.3 | project history matters, recent blockers matter slightly more |
| `confide` | 0.65 | 0.15 | surface the specific prior disclosure |
| `mixed` | 0.5 | 0.3 | default |

(Remaining weight in each row goes to `relevance_boost`.)

### 7.3 Structured aggregate queries (unchanged from v2, now explicitly the "structured retrieval" mechanism)

```sql
SELECT date, chunk_text FROM chunks
WHERE tags LIKE '%<tag>%' AND type = 'project-log' AND project = '<project>'
ORDER BY date ASC;
```

Counts and dates are passed into Call B as ground truth. The system prompt instructs the model to only state a frequency claim when this data is present — never estimate from `retrieved_chunks` alone (Principle 6).

---

## 8. Data Layer Details (carried over from v2, unchanged except where noted)

### 8.1 Indexer

Parses file-level frontmatter; if `type` is `daily`, `project-log`, or **`person`** (new — see §4.1), switches to section-mode and reads metadata from each block's inline comment rather than the file header. Chunks embedded and tagged with `embedding_model`/`embedding_version`, routed to `index.sqlite` or `secrets_index.sqlite` by sensitivity.

```sql
CREATE TABLE chunks (
  chunk_id TEXT PRIMARY KEY,
  file_path TEXT NOT NULL,
  entry_anchor TEXT,
  chunk_text TEXT NOT NULL,
  embedding BLOB NOT NULL,
  embedding_model TEXT NOT NULL,
  embedding_version TEXT NOT NULL,
  date TEXT, type TEXT, sensitivity TEXT,
  status TEXT,                    -- new: observation | hypothesis | fact | NULL (n/a outside /people/)
  confidence REAL,                -- new: for hypothesis/fact chunks
  people TEXT, projects TEXT, tags TEXT,
  mood TEXT, mood_score INTEGER,
  updated_at TEXT NOT NULL
);
```

### 8.2 Physical secrets separation

Unchanged from v2 — `secrets_index.sqlite` is a separate connection that normal-mode and `checkin`/`project`/`recall` retrieval code never holds a handle to. This remains true regardless of how rich the Interpreter's inference gets (Principle 3).

### 8.3 Embedding versioning

Unchanged from v2 — model/version tagged per chunk, query-time filter excludes mismatched vectors, re-index required on model upgrade.

### 8.4 Concurrency

Unchanged from v2 — per-file lock directory, single-writer append.

### 8.5 `/core/` and Person Model token budget

Extended from v2: the budget (default 3,000 tokens) now covers `/core/` **and** the loaded Person Model sections together, not `/core/` alone — the Person Model can grow large over years exactly like `/core/` can. Under budget, load everything relevant. Over budget: always load `system-notes.md` and any `fact`-status person-note sections in full (these are cheap and behavior-critical); load `hypothesis`-status sections only when their tags/people overlap with the current interpretation's entities, same relevance-filtering logic as chunk retrieval.

---

## 9. Prompt Assembly & the Main Model Call (Call B)

### 9.1 System prompt

```
You are a private reflection and memory companion for {user_name}.
You are not a therapist and have no clinical training or legal
confidentiality protections — if this ever matters (crisis, safety,
legal), say so plainly rather than implying otherwise.

You already have general conversational judgment. What follows is
ADDITIONAL, individual-specific context — use it to sharpen your
response, not to override good judgment when it conflicts with
what's actually happening in this message.

- Core facts about the user (curated, always true): {core_memory}
- What's known about this person specifically, with confidence levels
  — treat "hypothesis" items as probabilistic, not certain: {person_model}
- Retrieved relevant context from past entries: {retrieved_chunks}
- Structured aggregate data, if this is a pattern/frequency question: {aggregate_data}
- This turn's interpretation (what they likely need right now): {interpretation}
- Recent conversation: {recent_turns}

First, decide the appropriate conversational action via the
select_action tool — this is a real decision, not a formality:
consider whether the person needs an answer, a question, simple
acknowledgment, a challenge, or something else, per the interpretation
and needs above.

Then write your conversational reply, realizing that action in language.
Reference specific past entries naturally when relevant — don't
summarize the user's own life back at them generically.

Only make a frequency or pattern claim ("you've mentioned this three
times") when {aggregate_data} supports it. Only state a preference as
certain if its status is "fact," not "hypothesis."

Finally, call save_memory for anything worth remembering from this
exchange, or explicitly decline. Only use save_to: "secrets" if the
user has explicitly confirmed they want this held separately —
{mode_requires_confirmation} tells you whether that confirmation
still needs to happen; if so, ask, don't assume.
```

### 9.2 Two required tool calls, one text reply — same structural-guarantee reasoning as v2 §6.2

**`select_action`** (new):

```json
{
  "name": "select_action",
  "input_schema": {
    "type": "object",
    "properties": {
      "action": { "type": "string", "enum": [
        "ANSWER", "ASK", "ACKNOWLEDGE", "CHALLENGE", "CLARIFY",
        "REFLECT", "ENCOURAGE", "WAIT", "CHANGE_TOPIC", "RECALL",
        "EXPLAIN", "DO_NOTHING" ] },
      "based_on_hypotheses": { "type": "array", "items": { "type": "string" } },
      "predicted_user_reaction": { "type": "string" }
    },
    "required": ["action", "predicted_user_reaction"]
  }
}
```

This action vocabulary is explicitly provisional (per the source proposal) — not a finished first-principles ontology. Treat any request to "reduce and redefine the action space so each action is genuinely distinct" as a Phase 11+ research task, not a v1 blocker.

**`save_memory`** — unchanged from v2 §6.2, with `status`/`confidence` fields added to `frontmatter` when `save_to` is `person`.

Both are validated exactly as v2 §7 describes: schema failure → one retry with the error appended → dead-letter log on second failure, never silent drop.

---

## 10. Write-back Logic

### 10.1 Memory write-back

Unchanged from v2 §7, with one addition: `save_to: "person"` writes use the section-mode inline-metadata format from §4.1, not file-level frontmatter, and `content` for a hypothesis-type write must include `confidence` and at least one evidence date.

### 10.2 Prediction logging (new)

```
function logPrediction(select_action_output, conversation_id, turn_id):
  append to /_meta/predictions_log.jsonl:
    { turn_id, conversation_id, timestamp,
      action, predicted_user_reaction, based_on_hypotheses }
```

This file is working-memory scale (§4 table) — it is read by the *next* turn's Interpreter call (§5's `prediction_check`) and consumed/cleared into the weekly consolidation job (§11). It is never treated as durable vault content and is not indexed by the embedding pipeline.

---

## 11. Memory Consolidation

Weekly job, extended from v2 §5.3/§8:

1. Gather the week's `daily/` + `secrets/` entries (secrets summarized to pattern level only, never verbatim) and the week's `predictions_log.jsonl` entries.
2. Update or create `/themes/*.md` (relational memory) from the entries, as in v2.
3. **New:** for every hypothesis in `/people/*.md` referenced by at least one `based_on_hypotheses` entry in the week's predictions, compute an aggregate `prediction_error` rate for that hypothesis and adjust `confidence` up or down accordingly (a `low`/`none`-error week nudges confidence up; a `moderate`/`high`-error week nudges it down and flags the hypothesis for human review rather than silently discarding it).
4. Write all of this with `source: ai-generated`, same as v2 — none of it touches `/core/` or flips a `status` to `fact` without the human step in §13.

---

## 12. Evaluation

The cognition proposal's 8-dimension quality vector (`Q = [R_c, R_p, T, M, A, E, C, S]`) is a real research target, but computing it in full on every turn — likely requiring its own model judgment call per turn — would itself violate Principle 1 (don't context-stuff, don't over-spend on every turn what only needs periodic sampling). Split it:

- **Per-turn (cheap, automatic, logged to `/_meta/evaluation_log.jsonl`):** `prediction_error` (already computed per §5), whether `select_action` matched what actually happened, whether the `save_memory` call passed validation on the first try. No extra model call — derived from data already produced.
- **Periodic (weekly or on-demand, sampled):** a small batch of turns is scored against the full Q vector by a dedicated evaluation prompt, for the human to review trends in. This is a Phase 11 (optional) item, not part of v1's definition of done — flagged honestly as a research direction rather than claimed as solved.

---

## 13. Core Memory & Person Model Curation (human-in-the-loop)

Extended from v2 §8: the monthly/on-demand job now reviews **two** proposal sources side by side —

1. `/themes/*.md` + recent `/daily/` entries → proposed additions/edits to `/core/*.md` (unchanged from v2).
2. Hypotheses in `/people/*.md` whose confidence has crossed a threshold (e.g. ≥0.85, evidence_count ≥5) → proposed promotion from `status: hypothesis` to `status: fact`.

Both are written to `/core/_proposed/` with cited evidence (specific dates/entries), presented as a simple accept/reject list, and never applied automatically. This step must never be automatic — the Person Model colors every future conversation exactly as `/core/` does.

---

## 14. Model & Tooling Choices

| Component | v1 (build this first) | Later upgrade path |
|---|---|---|
| Interpreter (Call A) | Cheap/fast Claude call with the §5 schema as a tool, or a keyword+embedding heuristic for the earliest phases | Small dedicated local classifier model |
| Main model (Call B) | Claude API (Sonnet), called with `select_action` + `save_memory` tools defined | Local model (Ollama/MLX) for `confide`-mode turns only, gated by settings toggle |
| Decision-relevance retrieval | Structural boost from entity/tag overlap (§7.2) — an approximation | A learned relevance model trained on `predictions_log.jsonl` outcomes — retrieval that's actually informed by what changed past responses, not just topical overlap |
| Relational retrieval | Tag-graph traversal via SQL JOIN | Dedicated graph DB (e.g. Neo4j) once tag-graph stops scaling |
| Embeddings | `voyage-3-lite` or `text-embedding-3-small`, version-tagged | Local embedding model (`nomic-embed-text`) for full offline capability |
| Vector storage | Two SQLite DBs + `sqlite-vec`, or brute-force cosine for small vaults | LanceDB once either vault exceeds ~5k chunks |
| Evaluation | Per-turn cheap signals only (§12) | Full 8-dimension Q-vector periodic scoring |
| Server / Frontend / Sync | Unchanged from v2 §9 | Unchanged from v2 §9 |

---

## 15. Security & Privacy Requirements (non-negotiable, unchanged from v2 §10)

1. `/secrets/` and `secrets_index.sqlite` excluded from cloud sync by default; client-side encryption if sync is enabled.
2. Physically separate DB connection is the enforcement mechanism for "secrets don't leak" — and, per §3 of this merge, richer inference in the Interpreter is explicitly barred from being the thing that opens that connection. Only an explicit user confirmation does.
3. API keys never touch the client.
4. Secrets-tier log entries contain only `{timestamp, mode, file_path}`, never body content — this now also applies to `predictions_log.jsonl` entries derived from a `confide`-mode turn.
5. Visible, working export/delete from day one.
6. Plain-language first-run explanation of what leaves the device and when.
7. Dead-letter entries redact body content when the failed write's sensitivity was `secret`.

---

## 16. Build Phases

**Phase 0 — Vault scaffold**
Folder structure from §4, including `_meta/file.locks/`, `_meta/predictions_log.jsonl` (empty), `/core/_proposed/`. Confirm Obsidian renders the inline-meta comment format invisibly, for both daily and person notes.

**Phase 1 — Minimal write loop + basic Interpreter**
Server endpoint: message → Interpreter call (heuristic is fine at this phase — full LLM classification is not required yet) produces `mode` only (skip the full §5 schema for now) → main call with `save_memory` tool only (no `select_action` yet, no retrieval yet) → write to `/daily/`. Test: conversation produces a correctly formatted file; a malformed tool response is caught and retried, not dropped.

**Phase 2 — Indexer**
Section-mode vs file-mode parsing (including the new `person` type), chunking, embedding with version tags, routing to `index.sqlite`. Test: a person note with two hypothesis blocks produces two independently-tagged chunks.

**Phase 3 — Retrieval**
Two-stage retrieval with the mode-weighted alpha/beta table and the entity-overlap relevance boost (§7.2). Structured aggregate queries (§7.3). Test: a `recall`-mode query for something old-but-topically-matched outranks something recent-but-off-topic; confirm the relevance boost actually changes ranking versus similarity+recency alone on a constructed test case.

**Phase 4 — Sensitivity filtering + physical DB separation**
`secrets_index.sqlite` as a genuinely separate connection; `mode_requires_confirmation` gate implemented so a `confide`-looking message without explicit user confirmation stays in the normal tier. Test: automated grep-the-codepath test from v2, plus a new test that a high-emotional-intensity message *without* an explicit "keep this private" signal does not write to secrets.

**Phase 5 — Conversation Decision Engine + Person Model + Prediction Loop**
Full §5 Interpreter schema, `select_action` tool added to Call B, `predictions_log.jsonl` write-back (§10.2), `prediction_check` read-back at the start of the next turn. Test: manually script a two-turn exchange, confirm the second turn's Interpreter output correctly reflects `prediction_error` against the first turn's logged prediction.

**Phase 6 — Projects + structured aggregates**
Unchanged from v2 Phase 5, now also exercised by `recall`/`project` mode routing from the richer Interpreter.

**Phase 7 — Consolidation, extended**
Weekly job updates `/themes/*.md` (as v2) **and** adjusts hypothesis confidence from the week's `predictions_log.jsonl` (§11). Test: seed a week of turns with mostly `low`-error predictions tied to one hypothesis, confirm its confidence rises; seed mostly `high`-error, confirm it falls and gets flagged for review rather than silently deleted.

**Phase 8 — Core memory + Person Model curation**
Propose/accept/reject UI from §13, now handling both `/core/` proposals and hypothesis→fact promotions, each with cited evidence. Test: confirm nothing changes `status` to `fact` without explicit accept; confirm the §8.5 combined budget degradation path works when both `/core/` and the Person Model are inflated in a test fixture.

**Phase 9 — Hardening**
Export/delete, `/secrets/` encryption, audit log review, rate limiting, file-lock concurrency test, dead-letter review tooling — unchanged from v2 Phase 8.

**Phase 10 (optional) — Local model path**
Ollama/MLX for `confide`-mode turns, settings-gated — unchanged from v2 Phase 9.

**Phase 11 (optional, research) — Full evaluation + action-space refinement**
Periodic Q-vector scoring (§12); revisit the 12-item action vocabulary and attempt to reduce it to a genuinely minimal, non-overlapping set using accumulated `select_action`/`prediction_error` data as evidence for which actions actually behave distinctly. This is explicitly a research phase, not a shipping requirement.

---

## 17. Definition of Done for v1

A user can: have a conversation where the reply is preceded by an explicit, logged action decision rather than an implicit one; have the exchange correctly classified and saved to the right vault location with correctly-scoped metadata; ask "what did I say about my sister last month" and get an accurate answer sourced from real retrieved notes, with old-but-relevant results properly surfaced over new-but-irrelevant ones; log a project update and later get a synthesized observation about recurring blockers that's grounded in an actual count; have the system notice, over a week of turns, that a prediction about their preferences was repeatedly wrong, and see that hypothesis's confidence move accordingly without ever silently becoming a stated fact; confide something explicitly marked secret that never surfaces in unrelated conversations, verifiably, because the code path that would need to leak it doesn't exist. That's the bar — build to that, not past it, before Phase 11's research items.
