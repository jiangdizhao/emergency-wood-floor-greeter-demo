# Benchmark v5.1 — Compact local-first cascade

## Why v5.1 exists

Benchmark v5 showed that the original Qwen parser generated hundreds of audit tokens, took about 6 seconds per turn, and used a gate that both accepted incomplete parses and escalated correct parses. Benchmark v5.1 changes the parser and the evaluation rather than adding case-specific routing rules.

## Main changes

### Compact one-pass parser

Every provider now returns only:

```json
{
  "intent": "provide_or_modify_needs",
  "is_question": false,
  "explicit_self_context": true,
  "recommendation_requested": false,
  "actions": [
    {
      "kind": "set_field",
      "name": "has_pets",
      "value": "no",
      "evidence": "家里没养猫也没养狗"
    }
  ],
  "uncertain": false,
  "confidence": 0.95
}
```

The model no longer generates natural-language coverage explanations, scope, clarification prose, repeated entity arrays, or required empty update arrays. Qwen output is capped at 500 tokens.

### Backend-owned scope and normalization

Before parsing, ASR whitespace is removed, so `S P C`, `灰 色`, and character-spaced Chinese can be parsed consistently. The backend determines `persistent` versus `turn_only`; provider metadata does not directly control database writes.

### Completeness gate

The gate uses domain claims detected from the normalized utterance:

- room and budget values;
- pets, floor heating, children, elderly, and humidity;
- style versus color;
- named priorities and their level;
- product/color rejection actions;
- comparison product count;
- evidence, enum, conflict, and semantic-coherence checks.

Harmless empty/noise actions are removed without automatically escalating. Missing explicit claims, dangerous rejected actions, semantic contradictions, low confidence, and provider uncertainty trigger escalation.

### Split evaluation

The report separates:

- `hard_task_pass`: intent, recommendation flag, entities, required actions, scope, and persistent-state safety;
- `metadata_pass`: `explicit_self_context` agreement only;
- `state_pollution_count`;
- `critical_state_pollution_count`;
- `gate_false_accept`;
- `gate_false_reject`.

This prevents a metadata disagreement from being counted as a business failure while still preserving it for diagnosis.

## API key handling

The script does not accept an API key argument. It reads `OPENAI_API_KEY` only from the current process environment and never writes it to the report.

```powershell
$secureKey = Read-Host "OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
Remove-Variable secureKey
```

Remove it after testing:

```powershell
Remove-Item Env:OPENAI_API_KEY
```

## Pull and verify

```powershell
cd F:\emergency-wood-floor-greeter-demo
git pull

python -m py_compile `
  .\benchmarks\local_llm_dialogue_benchmark_v5_1.py

python .\benchmarks\local_llm_dialogue_benchmark_v5_1.py --list-cases
```

## Step 1 — Compact Qwen smoke test

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v5_1.py `
  --mode qwen_only `
  --case G01_colloquial_living_room `
  --case G11_pet_correction `
  --case G21_generic_comparison_scope `
  --case G26_character_spacing `
  --verbose `
  --report .\benchmarks\results\qwen35_4b_v5_1_smoke.json
```

Check the Qwen `output_tokens` and latency against v5. The intended direction is substantially below the previous 400–600 output-token responses and 6-second average.

## Step 2 — Recommended comparison

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v5_1.py `
  --mode qwen_only `
  --mode luna_only `
  --mode qwen_luna `
  --repeat 1 `
  --report .\benchmarks\results\qwen_luna_v5_1_comparison_run1.json
```

Provider calls are cached within the run. The same provider response is reused across modes, avoiding duplicate billing.

## Step 3 — Full five-mode comparison

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v5_1.py `
  --all-modes `
  --repeat 1 `
  --report .\benchmarks\results\cross_provider_v5_1_all_modes_run1.json
```

A non-zero process exit code means at least one selected mode had a hard-task failure. The JSON report is still written.

## Step 4 — Stable cascade run

Run this only after the first report has been reviewed:

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v5_1.py `
  --mode qwen_luna `
  --mode qwen_luna_terra `
  --repeat 3 `
  --report .\benchmarks\results\cross_provider_v5_1_cascades_repeat3.json
```

## Gate thresholds

Defaults:

```text
--gate-min-confidence 0.80
--gate-min-claim-coverage 1.00
```

The claim-coverage threshold is intentionally strict because the gate only creates claims for high-confidence domain entities. Do not tune thresholds against individual case IDs. Compare aggregate false-accept and false-reject rates.

## What to inspect

The most important v5.1 fields are:

```text
summary_by_mode.*.hard_task_pass_rate
summary_by_mode.*.metadata_pass_rate
summary_by_mode.*.state_pollution_count
summary_by_mode.*.critical_state_pollution_count
gate_diagnostics_by_provider.qwen.false_accept
gate_diagnostics_by_provider.qwen.false_reject
gate_diagnostics_by_provider.qwen.gate_accuracy
results[*].attempts[*].usage.output_tokens
results[*].attempts[*].missing_claims
results[*].attempts[*].gate_reasons
```

The local-first cascade is only worth adopting when all of the following improve together:

1. Qwen mean latency and output tokens fall materially;
2. Qwen gate false-accept rate falls below v5;
3. hard-task pass rate approaches Luna-only;
4. critical state pollution remains zero or near zero;
5. cloud escalation and total cost remain meaningfully below Luna-only.
