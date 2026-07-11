# Local/Cloud Dialogue Benchmark v5 — Cross-provider cascade

## Purpose

Benchmark v5 compares one-pass structured parsing across:

- `qwen_only`: local `qwen3.5:4b`
- `luna_only`: OpenAI `gpt-5.6-luna`
- `terra_only`: OpenAI `gpt-5.6-terra`
- `qwen_luna`: Qwen first, Luna only when the provider-neutral validation gate rejects the Qwen result
- `qwen_luna_terra`: Qwen first, then Luna, then Terra when each earlier result fails the same gate

The suite reuses all 30 Benchmark v4 holdout cases. It does **not** add case-specific phrase routing. Every provider receives the same combined JSON Schema and the same single-turn parsing prompt. The gate uses only provider-neutral checks:

- JSON/schema-compatible fields
- canonical enum values
- verbatim evidence
- duplicate/conflicting updates
- intent/recommendation consistency
- provider-declared confidence and clarification need
- provider-declared coverage items and measured text coverage

This design measures the trade-off among local latency, cloud accuracy, escalation rate, and API cost without hiding weak provider output behind hand-written sentence rules.

## Security and privacy

The script never accepts an API key as a command-line argument. It reads `OPENAI_API_KEY` from the current process environment and never prints or writes the key to the JSON report.

Only the benchmark utterance, its small structured state, the parsing prompt, and JSON Schema are sent to OpenAI. No product database or repository file is uploaded.

For a temporary PowerShell session:

```powershell
$secureKey = Read-Host "OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
Remove-Variable secureKey
```

This environment variable disappears when that terminal is closed. Do not use `setx` for the benchmark unless persistent storage is explicitly desired.

After testing:

```powershell
Remove-Item Env:OPENAI_API_KEY
```

## Requirements

- Ollama is running at `http://127.0.0.1:11434`
- `qwen3.5:4b` is installed
- Python 3.10+
- Internet access for OpenAI modes
- An OpenAI API key with access to the configured models

The script uses only the Python standard library. It does not require the OpenAI Python SDK.

## Step 1 — Local-only smoke test

This does not require an OpenAI key:

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v5.py `
  --mode qwen_only `
  --case G01_colloquial_living_room `
  --case G15_reason_without_why_keyword `
  --verbose `
  --report .\benchmarks\results\qwen35_4b_v5_local_smoke.json
```

## Step 2 — OpenAI connectivity smoke test

Set `OPENAI_API_KEY` in the current terminal, then run two selected cases:

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v5.py `
  --mode luna_only `
  --case G01_colloquial_living_room `
  --case G15_reason_without_why_keyword `
  --verbose `
  --report .\benchmarks\results\gpt56_luna_v5_smoke.json
```

## Step 3 — Recommended first comparison

This compares the local baseline, Luna baseline, and the practical two-level cascade. Provider calls are cached inside one run, so the same Luna response is reused across modes rather than billed twice.

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v5.py `
  --mode qwen_only `
  --mode luna_only `
  --mode qwen_luna `
  --repeat 1 `
  --report .\benchmarks\results\qwen_luna_v5_comparison_run1.json
```

A non-zero exit code is expected whenever any compared mode has a failed case. The JSON report is still written.

## Step 4 — Full five-mode comparison

This calls Qwen, Luna, and Terra once per case and reuses those outputs across all five modes:

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v5.py `
  --all-modes `
  --repeat 1 `
  --report .\benchmarks\results\cross_provider_v5_all_modes_run1.json
```

Because `qwen_only` is intentionally included as a weak baseline, the process may return exit code 1 even when a cascade performs well.

## Stable-run comparison

After the first result is analysed:

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v5.py `
  --mode qwen_luna `
  --mode qwen_luna_terra `
  --repeat 3 `
  --report .\benchmarks\results\cross_provider_v5_cascades_repeat3.json
```

## Useful filters

List all inherited v4 cases:

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v5.py --list-cases
```

Run one category:

```powershell
python .\benchmarks\local_llm_dialogue_benchmark_v5.py `
  --mode qwen_luna `
  --category scope `
  --verbose `
  --report .\benchmarks\results\qwen_luna_v5_scope.json
```

Available categories:

```text
paraphrase
correction_negation
intent_boundary
scope
asr_noise
multi_intent
```

## Gate tuning

Defaults:

```text
--gate-min-confidence 0.80
--gate-min-coverage   0.60
```

The gate is deliberately provider-neutral. Lower thresholds reduce cloud escalation but may allow incomplete local parses. Higher thresholds increase escalation and cost. Do not tune these thresholds against individual sentences; tune them using aggregate false-accept and unnecessary-escalation rates.

## Report fields

Each mode records:

- final pass rate and category pass rates
- selected provider counts
- escalation rate
- end-to-end sequential latency
- provider attempts and gate reasons
- input/output token counts
- estimated OpenAI cost
- sanitized updates and rejected unsafe items

OpenAI cost is estimated using configurable standard per-million-token prices. The default assumptions embedded in the script are:

```text
gpt-5.6-luna:  input $1.00 / MTok, output $6.00 / MTok
gpt-5.6-terra: input $2.50 / MTok, output $15.00 / MTok
```

Override them when prices change:

```powershell
--luna-input-price 1.0 `
--luna-output-price 6.0 `
--terra-input-price 2.5 `
--terra-output-price 15.0
```

The estimate uses total input/output tokens and does not apply cached-input discounts.

## Interpretation

The main production candidate is `qwen_luna`, not the best cloud-only score in isolation. Evaluate:

1. final pass rate, especially state-pollution failures;
2. escalation rate;
3. P50/P95 latency;
4. selected-provider distribution;
5. total and per-turn estimated cost;
6. cases where the gate accepted a wrong Qwen parse;
7. cases where the gate unnecessarily escalated a correct Qwen parse.

`qwen_luna_terra` is useful only when Terra materially fixes Luna failures at an acceptable additional latency and cost.
