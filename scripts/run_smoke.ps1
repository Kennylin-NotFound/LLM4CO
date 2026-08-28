$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $PreviousPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = Join-Path $ProjectRoot "src"

    python -m pytest
    if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE" }

    python -m cover_opt validate-contract --contract research_contract.yaml
    if ($LASTEXITCODE -ne 0) { throw "contract validation failed" }

    python -m cover_opt generate-walker `
        --config configs/scenarios/walker_dynamic.yaml `
        --time-slot 0 `
        --output artifacts/reports/walker_slot_0000.json
    if ($LASTEXITCODE -ne 0) { throw "Walker scenario generation failed" }

    python -m cover_opt simulate-static `
        --scenario configs/scenarios/small_static.yaml `
        --placement configs/placements/small_static_previous.yaml `
        --output artifacts/reports/small_static_result.json
    if ($LASTEXITCODE -ne 0) { throw "static simulation failed" }

    python -m cover_opt run-scripted-search `
        --config configs/experiments/method_smoke.yaml `
        --output artifacts/reports/method_smoke.json
    if ($LASTEXITCODE -ne 0) { throw "scripted method search failed" }

    python -m cover_opt run-offline `
        --config configs/experiments/offline_smoke.yaml `
        --llm mock
    if ($LASTEXITCODE -ne 0) { throw "mock smoke run failed" }

    python -m cover_opt run-offline `
        --config configs/experiments/offline_smoke.yaml `
        --llm replay `
        --replay-file tests/fixtures/llm/replay_offline_smoke.json
    if ($LASTEXITCODE -ne 0) { throw "replay smoke run failed" }
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
    Pop-Location
}
