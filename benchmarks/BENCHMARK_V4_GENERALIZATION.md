# Local LLM Dialogue Benchmark v4 — Generalization Holdout

## Purpose

Benchmark v3 proved that the current hybrid pipeline is stable on its original ten regression cases. Benchmark v4 evaluates whether that same pipeline generalizes to **previously unseen wording**.

The v4 runner imports `benchmarks/local_llm_dialogue_benchmark.py` and deliberately does **not** modify the v3 prompts, schemas, resolver, deterministic recovery rules, or validation guard. This preserves a meaningful holdout test. Do not add v4 phrases to the v3 rules before recording the initial result.

## Coverage

The suite contains 30 cases across six categories:

- `paraphrase`: colloquial wording and synonyms
- `correction_negation`: corrections, explicit negatives, and priority changes
- `intent_boundary`: reason vs comparison vs rejection vs product question
- `scope`: generic hypothetical conditions vs persistent customer state
- `asr_noise`: missing punctuation, character spacing, and terminology variants
- `multi_intent`: one utterance containing several valid actions

In addition to the v3 checks, v4 verifies:

- `recommendation_requested`
- `explicit_self_context`
- whether the fact-extraction stage should run or be skipped
- all accepted evidence is verbatim from the user utterance
- accepted field values are valid and non-empty
- no conflicting accepted updates exist
- category-level pass rates
- raw LLM intent accuracy versus final routed accuracy
- dependency on deterministic recoveries versus model-only accepted facts

## Run the complete holdout once

From the repository root:

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v4.py `
  --model qwen3.5:4b `
  --repeat 1 `
  --report .\benchmarks\results\qwen35_4b_v4_generalization_run1.json
```

A non-zero process exit code is expected when one or more holdout cases fail. The JSON report is still written. A failure is a benchmark finding, not a script crash.

## Verbose diagnosis

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v4.py `
  --model qwen3.5:4b `
  --repeat 1 `
  --verbose `
  --report .\benchmarks\results\qwen35_4b_v4_generalization_verbose.json
```

## List cases

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v4.py --list-cases
```

## Run one category

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v4.py `
  --category intent_boundary `
  --verbose `
  --report .\benchmarks\results\qwen35_4b_v4_intent_boundary.json
```

Available categories are:

```text
paraphrase
correction_negation
intent_boundary
scope
asr_noise
multi_intent
```

## Run selected cases

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v4.py `
  --case G15_reason_without_why_keyword `
  --case G23_generic_recommendation_scope `
  --verbose
```

## Interpretation

Use two separate scores:

1. **Final pipeline pass rate** — whether routing, extraction, deterministic recovery, and guard collectively produce the expected safe result.
2. **Raw intent accuracy** — whether the first LLM classifier alone selects the expected intent.

A high final pass rate with low raw intent accuracy means the hybrid system is safe on the tested cases but still depends heavily on hand-built routing. The report also counts accepted facts originating from deterministic recovery and those accepted only from the LLM.

Suggested initial interpretation:

- `>= 90%`: strong holdout result; inspect remaining failures individually
- `75–90%`: usable foundation, but targeted architecture fixes are needed
- `< 75%`: current rules and prompts are overfitted to v3 wording; do not integrate the parser unchanged

Do not tune against every individual sentence. Group failures by semantic capability, then implement the smallest general mechanism that resolves the category without breaking v3.

## After the first run

1. Commit the untouched v4 result file.
2. Analyse failures by category and root cause.
3. Improve the production parser using general mechanisms rather than case-specific phrases.
4. Re-run both benchmarks:

```powershell
python .\benchmarks\local_llm_dialogue_benchmark.py `
  --model qwen3.5:4b `
  --repeat 3 `
  --report .\benchmarks\results\qwen35_4b_v3_regression_after_changes.json

python .\benchmarks\local_llm_dialogue_benchmark_v4.py `
  --model qwen3.5:4b `
  --repeat 3 `
  --report .\benchmarks\results\qwen35_4b_v4_generalization_repeat3.json
```

The v3 suite protects established behavior; the v4 suite measures generalization.
