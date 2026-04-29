# Vision regression parity thresholds

## Scope
Integration test `app/tests/integration/test_multimodal_endpoint_parity.py` validates representative multimodal image-cases across:
- `POST /ask`
- `POST /v1/chat/completions`

## Representative cases
The suite runs 3 image scenarios:
1. marker screenshot (`tc_marker`) with deterministic error code facts;
2. UI form screenshot (`tc_ui_form`) with deterministic validation facts;
3. unknown/generic screenshot (`tc_unknown`) to cover fallback behavior.

## Metrics
For each case and each endpoint test computes:
- `recall`: share of golden facts present in answer;
- `hallucination`: share of forbidden facts present in answer.

Metrics are computed by shared evaluator module `app/tests/integration/vision_eval.py` to keep one formula for both endpoints.

## Quality gates
Current thresholds in CI:
- minimum average recall for each endpoint: `>= 0.60`;
- recall degradation guard: `/v1/chat/completions` recall cannot be lower than `/ask` by more than `0.10` (10 p.p.);
- hallucination average for each endpoint: `== 0.0`;
- request errors: zero (every request must return HTTP 200).

## Rationale
- `0.60` minimum recall keeps the smoke-test stable for deterministic mocked multimodal content, while still catching extraction regressions.
- `10 p.p.` chat-vs-ask guard protects compatibility of OpenAI endpoint with canonical `/ask` behavior.
- Zero hallucination and zero request errors keep regression signal strict for correctness and reliability.

## CI integration
Test is part of the main GitHub Actions pipeline (`.github/workflows/tests.yml`) because the workflow runs `pytest -q` for all tests.
