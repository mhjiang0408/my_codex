---
name: research-lit
description: Search and analyze research papers, find related work, summarize key ideas. Use when user says "find papers", "related work", "literature review", "what does this paper say", or needs to understand academic papers.
allowed-tools: Bash(*), Read, WebSearch, WebFetch, Write, Agent
---

# Research Literature Review

Research topic: $ARGUMENTS

## Workflow

### Step 1: Search
- Use WebSearch to find recent papers on the topic
- Check arXiv, Semantic Scholar, Google Scholar
- You can use the `huggingface-paper-pages` skill to search paper
- Focus on papers from last 2 years unless studying foundational work
- If generic HTML search endpoints are flaky or timeout in the current environment, fall back to:
  - arXiv API for paper discovery and abstracts
  - official GitHub README or raw source files for implementation evidence
  - project pages or docs only when they are official sources for the method

### Step 2: Analyze Each Paper
For each relevant paper, extract:
- **Problem**: What gap does it address?
- **Method**: Core technical contribution (1-2 sentences)
- **Results**: Key numbers/claims
- **Relevance**: How does it relate to the user's stated topic? If "our work" is unspecified, anchor this field to the current search topic instead of inventing a project context.

### Step 3: Synthesize
- Group papers by approach/theme
- Identify consensus vs disagreements in the field
- Find gaps that our work could fill

### Step 4: Output
Present as a structured literature table:

```
| Paper | Venue | Method | Key Result | Relevance to Us |
|-------|-------|--------|------------|-----------------|
```

Formatting requirements:
- `Paper`: include title and enough citation context to identify the work; include authors/year in surrounding text if not in the cell.
- `Venue`: must distinguish `peer-reviewed venue/status` from `preprint`, and should include a concrete date when recency matters, e.g. `ICLR 2026 Poster` or `arXiv preprint (2026-02-26)`.
- `Method`: for benchmark-centric papers, describe the benchmark/task design rather than generic model architecture.
- `Key Result`: include the most decision-useful number or claim; if no headline metric is available, say so explicitly.
- `Relevance to Us`: if there is no shared project context, rewrite this as relevance to the user's topic, such as `与 long-horizon benchmark 检索的相关性`.
- If the user asks for a recent window, sort papers primarily by relevance and secondarily by date, and state the exact date window in the prose summary.

Plus a narrative summary of the landscape (3-5 paragraphs) that includes:
- search scope and inclusion criteria,
- major thematic groups,
- notable trends or disagreements,
- gaps or opportunities relevant to the user's topic.

### Step 5: Save (if requested)
- Save paper PDFs to `literature/` or `papers/`
- Update related work notes in project memory
- If task-level or repository-level instructions require external sync (for example Feishu/Lark), treat that sync as part of the required delivery rather than an optional digest.
- For required external sync, include:
  - the literature table itself,
  - any supplementary paper notes that affect prioritization,
  - the thematic grouping / topic judgment used in the narrative summary,
  - the exact date window and inclusion criteria when the search is time-bounded.
- If one message would be too dense or too long, send the content as multiple messages instead of collapsing it into a short summary.

## Key Rules
- Always include paper citations (authors, year, venue)
- Distinguish between peer-reviewed and preprints
- Be honest about limitations of each paper
- Note if a paper directly competes with or supports our approach
- When the user asks how a method is actually trained in practice, prefer official implementation evidence over abstract-only inference whenever code is available.
- When the user asks how to obtain a benchmark ground-truth artifact rather than how to improve a model, prioritize the official paper, official dataset card, official README/docs, and official harness in that order; explicitly distinguish "read the public artifact from the dataset" from "reconstruct the artifact from upstream sources such as a PR diff."
- When external sync is required, keep the synced content semantically aligned with the main answer; do not omit the main table or core judgments unless the user explicitly asks for a shorter sync.

## Project-Specific Clarification Pattern
- When the user distinguishes `internalized state awareness` from `context injection`, do not frame the task as retrieval-augmented memory or longer-context compensation.
- Reframe the literature review around `state representation`, `state transition`, `dependency frontier tracking`, `hierarchical state abstraction`, and `action validity conditioned on current state`.
- For such requests, explicitly separate:
  - inference-time context stuffing / memory retrieval
  - model-internal state modeling learned through midtraining
- Favor recommendations about trajectory data with latent/explicit state supervision, transition consistency, invalid-action negatives, rollback / replanning signals, and benchmarks that require tracking current world/task state.
- When the user asks whether training data was actually utilized, do not default to final task score as the main answer.
- First separate:
  - `internalization-layer evaluation`: did the model learn the targeted latent structure or transition rule
  - `outer-task evaluation`: did that internalization transfer to final repo/task performance
- If the user emphasizes `feature evolution`, `intermediate states`, or `long-horizon code state transition`, recommend an internalization-first benchmark stack before final task benchmarks.
- For these requests, explicitly suggest ablations such as:
  - no-evolution baseline
  - before/after-only training
  - shuffled-trajectory training
  - final-patch-only training
- Treat the following benchmark families as the default template for such evaluations:
  - transition discrimination
  - intermediate-state prediction
  - evolution ordering / attribution
  - counterfactual evolution consistency
- When the user explicitly says to first survey existing benchmarks and only then discuss how to build one, do not start from generic evaluation frameworks or training recipes.
- In that case, structure the output as a Chinese `科研备忘录` when the user requests memo style, and organize it in this order:
  - existing benchmarks that are directly usable
  - benchmarks that are only partially useful / proxy evidence
  - the missing benchmark capabilities
  - how to construct a new benchmark if needed
- For this pattern, each benchmark entry should explicitly answer:
  - what it measures
  - why it is relevant to the user's state/evolution question
  - whether it can be directly used to answer the question
  - what gap remains if it cannot
