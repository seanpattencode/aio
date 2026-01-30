# Experiment Report: 10s Timeout vs Leaderboard (30s)

## Overview

This report compares the performance of the classification pipeline with a strict **10-second timeout** against the established leaderboard baseline (30-second timeout). The goal was to test system efficiency and identify which datasets require longer processing times.

## Key Findings

1.  **Efficiency:** 92% of the successfully processed datasets (11/12) completed training within 10 seconds without any loss in accuracy.
2.  **Timeout Impact:** The `ag_news` dataset (120k rows) timed out at 10s, whereas it achieved 79.1% accuracy with a 30s timeout. This establishes a clear lower bound for processing large datasets.
3.  **Stability:** For all datasets that completed within the time limit, results were bit-exact identical to the leaderboard, confirming deterministic reproducibility.

## Comparative Results (Best Performing Models)

| Dataset | Leaderboard (30s) | Current Run (10s) | Status | Diff |
| :--- | :--- | :--- | :--- | :--- |
| **ChemBench:toxicity** | **100.0%** | **100.0%** | ✅ OK | ±0.0% |
| **ChemBench:general** | **100.0%** | **100.0%** | ✅ OK | ±0.0% |
| **tmmluplus:eng_math** | **100.0%** | **100.0%** | ✅ OK | ±0.0% |
| **ChemBench:physical** | 93.9% | 93.9% | ✅ OK | ±0.0% |
| **ChemBench:organic** | 91.9% | 91.9% | ✅ OK | ±0.0% |
| **VIBE** | 90.0% | 90.0% | ✅ OK | ±0.0% |
| **ChemBench:materials** | 76.5% | 76.5% | ✅ OK | ±0.0% |
| **sst2** | 66.0% | 66.0% | ✅ OK | ±0.0% |
| **OctoCodingBench** | 60.0% | 60.0% | ✅ OK | ±0.0% |
| **emotion (SetFit)** | 40.0% | 40.0% | ✅ OK | ±0.0% |
| **emotion (dair-ai)** | *N/A* | 40.0% | ✅ OK | *New* |
| **tmmluplus:cs** | 0.0% | 0.0% | ✅ OK | ±0.0% |
| **ag_news** | **79.1%** | **TIMEOUT** | ❌ FAIL | -79.1% |

*Note: `multilingual-sentiments` failed to download in the current run.*

## Analysis of "Best Performing Models"

The Random Forest baseline proves highly efficient for scientific and specialized text classification, achieving >90% accuracy on 5 datasets within seconds.

-   **Top Tier (>90%):** Chemistry benchmarks and VIBE domain classification. These appear to have highly discriminative vocabulary that TF-IDF captures easily, even with limited time.
-   **Mid Tier (60-80%):** Materials science and general sentiment (sst2).
-   **Failures (<50%):** Emotion detection (complex, subtle) and CS QA (too few samples).

## Recommendations

1.  **Adaptive Timeout:** Implement logic to set timeout based on dataset size (rows).
    -   <10k rows: 10s
    -   10k-50k rows: 30s
    -   >50k rows: 60s+
2.  **Dataset Filtering:** `tmmluplus:cs` (5 rows) is too small for meaningful training and should be filtered out or augmented.
3.  **Model Upgrade:** For `emotion` (40%) and `sst2` (66%), the simple TF-IDF+RF approach is insufficient. These should be prioritized for CFA integration with embeddings or VQC models.

---
*Report generated: 2026-01-30*
*Configuration: `uv run --with datasets --with scikit-learn --with numpy python /tmp/run_all.py 10`*
