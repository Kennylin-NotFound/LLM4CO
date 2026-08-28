param(
    [switch]$Live,
    [switch]$Verify
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$OutputRoot = Join-Path $ProjectRoot "artifacts/interview_demo"
$PreviousPythonPath = $env:PYTHONPATH
$PreviousApiKey = $env:DEEPSEEK_API_KEY

function Invoke-CoverOpt {
    param([string[]]$Arguments)

    & python -m cover_opt @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "cover_opt failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
}

Push-Location $ProjectRoot
try {
    $SourceRoot = Join-Path $ProjectRoot "src"
    if ([string]::IsNullOrWhiteSpace($PreviousPythonPath)) {
        $env:PYTHONPATH = $SourceRoot
    }
    else {
        $env:PYTHONPATH = "$SourceRoot;$PreviousPythonPath"
    }

    New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

    if ($Verify) {
        & python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

        & python -m compileall -q src
        if ($LASTEXITCODE -ne 0) { throw "compileall failed" }
    }

    Invoke-CoverOpt -Arguments @(
        "validate-contract",
        "--contract", "research_contract.yaml"
    )
    Invoke-CoverOpt -Arguments @(
        "validate-experiment-protocol",
        "--protocol", "configs/experiments/formal_experiment_protocol.yaml"
    )
    Invoke-CoverOpt -Arguments @(
        "run-baseline-smoke",
        "--config", "configs/experiments/baseline_smoke.yaml",
        "--output", "artifacts/interview_demo/baseline_smoke.json"
    )
    Invoke-CoverOpt -Arguments @(
        "run-replay-search",
        "--config", "configs/experiments/replay_method_smoke.yaml",
        "--output", "artifacts/interview_demo/replay_search.json"
    )
    Invoke-CoverOpt -Arguments @(
        "run-ablation-suite",
        "--config", "configs/experiments/ablation_control_suite.yaml",
        "--output", "artifacts/interview_demo/ablation_suite.json"
    )
    Invoke-CoverOpt -Arguments @(
        "run-ablation-suite",
        "--config", "configs/experiments/method_completion_suite.yaml",
        "--output", "artifacts/interview_demo/method_completion_suite.json"
    )
    Invoke-CoverOpt -Arguments @(
        "run-counterexample-replay-campaign",
        "--config", "configs/experiments/counterexample_replay_campaign.yaml",
        "--output", "artifacts/interview_demo/counterexample_replay_campaign.json"
    )

    $LiveOutput = $null
    if ($Live) {
        if ([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
            $env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable(
                "DEEPSEEK_API_KEY",
                "User"
            )
        }
        if ([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
            throw "DEEPSEEK_API_KEY is not available in the process or User environment"
        }

        Invoke-CoverOpt -Arguments @(
            "run-deepseek-search-smoke",
            "--config", "configs/experiments/deepseek_v4pro_search_smoke.yaml",
            "--output", "artifacts/interview_demo/deepseek_live_search.json"
        )
        $LiveOutput = "artifacts/interview_demo/deepseek_live_search.json"
    }

    $Baseline = Get-Content -Raw -Encoding UTF8 `
        "artifacts/interview_demo/baseline_smoke.json" | ConvertFrom-Json
    $Replay = Get-Content -Raw -Encoding UTF8 `
        "artifacts/interview_demo/replay_search.json" | ConvertFrom-Json
    $Ablation = Get-Content -Raw -Encoding UTF8 `
        "artifacts/interview_demo/ablation_suite.json" | ConvertFrom-Json
    $MethodCompletion = Get-Content -Raw -Encoding UTF8 `
        "artifacts/interview_demo/method_completion_suite.json" | ConvertFrom-Json
    $ReplayCampaign = Get-Content -Raw -Encoding UTF8 `
        "artifacts/interview_demo/counterexample_replay_campaign.json" | ConvertFrom-Json

    $Summary = [ordered]@{
        evidence_status = "interview_demo_control_flow_evidence_not_performance_claim"
        contract_validated = $true
        protocol_validated = $true
        baseline = [ordered]@{
            oracle_optimality_proven = $Baseline.oracle_optimality_proven
            solvers = @($Baseline.solver_results | ForEach-Object { $_.solver_name })
        }
        replay_search = [ordered]@{
            stop_reason = $Replay.search_result.stop_reason
            best_candidate_id = $Replay.search_result.best_candidate_id
            evaluator_calls = $Replay.search_result.statistics.evaluator_calls
            accepted_patches = $Replay.search_result.statistics.accepted_patches
            counterexamples = @($Replay.search_result.counterexamples).Count
        }
        ablation = [ordered]@{
            passed = $Ablation.suite_result.passed
            passed_variants = $Ablation.suite_result.passed_variant_count
            total_variants = $Ablation.suite_result.variant_count
        }
        method_completion = [ordered]@{
            passed = $MethodCompletion.suite_result.passed
            passed_variants = $MethodCompletion.suite_result.passed_variant_count
            total_variants = $MethodCompletion.suite_result.variant_count
        }
        counterexample_replay_campaign = [ordered]@{
            passed = $ReplayCampaign.passed
            seed_runs = $ReplayCampaign.campaign_result.statistics.seed_runs
            scenario_replays = $ReplayCampaign.campaign_result.statistics.scenario_replays
            resolved_counterexamples = $ReplayCampaign.campaign_result.statistics.resolved_counterexamples
            total_llm_calls = $ReplayCampaign.campaign_result.statistics.total_llm_calls
        }
        live_requested = [bool]$Live
        live_artifact = $LiveOutput
    }

    $SummaryPath = Join-Path $OutputRoot "demo_summary.json"
    $Summary | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $SummaryPath
    Write-Host "COVER-Opt interview demo completed."
    Write-Host "Summary: $SummaryPath"
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
    $env:DEEPSEEK_API_KEY = $PreviousApiKey
    Pop-Location
}
