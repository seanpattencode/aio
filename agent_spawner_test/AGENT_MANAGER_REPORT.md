# Agent Manager System Report

## Overview

This system spawns multiple Claude CLI agents in parallel to generate and run machine learning experiments across HuggingFace datasets, comparing Quantum and Classical models using Combinatorial Fusion Analysis (CFA).

---

## System Architecture

```
agent_spawner_test/
├── agent_spawner.py       # Sequential agent runner (streaming output)
├── command_generator.py   # Parallel command generator
├── run_all.py             # Execute generated scripts
├── CONTINUE_PROMPT.md     # Full context for agents
├── small_datasets.csv     # 167 HuggingFace datasets
├── generated_commands/    # Output: Python scripts (10 generated)
└── results/               # Output: Execution results
```

---

## Components

### 1. `agent_spawner.py` - Sequential Runner with Streaming

**Purpose:** Run one agent at a time with full visibility of what it's doing.

**Features:**
- Streams JSON output in real-time (`--output-format stream-json`)
- Shows tool calls: `[TOOL: Read]`, `[TOOL: Bash]`, etc.
- 10-minute timeout per dataset
- Ctrl+C to skip/stop

**Usage:**
```bash
python agent_spawner.py --list       # List 167 datasets
python agent_spawner.py --all        # Run all sequentially
python agent_spawner.py ChemBench    # Run single dataset
```

### 2. `command_generator.py` - Parallel Generator

**Purpose:** Spawn multiple agents in parallel to generate training scripts.

**Features:**
- Runs N agents simultaneously (default: 3)
- 2-minute timeout per generation
- Saves output to `generated_commands/*.txt`

**Usage:**
```bash
python command_generator.py -n 10 -p 5   # 10 datasets, 5 parallel
python command_generator.py -n 167 -p 10 # All datasets, 10 parallel
```

### 3. `run_all.py` - Script Executor

**Purpose:** Execute all generated Python scripts and collect results.

**Features:**
- Extracts Python from markdown code blocks
- Runs with `uv run --with datasets --with scikit-learn`
- Saves results to `results/*.txt`
- Generates `SUMMARY.txt`

**Usage:**
```bash
python run_all.py
```

---

## Current Progress

### Completed ✅
1. **Agent spawner with streaming** - Working, shows real-time tool calls
2. **Parallel command generator** - Working, 10/10 success rate
3. **167 datasets loaded** from `small_datasets.csv`
4. **10 training scripts generated** in `generated_commands/`

### Tested Results
| Metric | Value |
|--------|-------|
| Datasets available | 167 |
| Scripts generated | 10 |
| Generation success rate | 100% |
| Execution success rate | 0% (scripts need fixes) |

### Generated Scripts (10)
```
generated_commands/
├── CodeMixBench_CodeMixBench.txt
├── GilatToker_Liberty_Disease.txt
├── MiniMaxAI_OctoCodingBench.txt
├── MiniMaxAI_VIBE.txt
├── ai_hyz_MemoryAgentBench.txt
├── google_FACTS_grounding_public.txt
├── google_simpleqa_verified.txt
├── ikala_tmmluplus.txt
├── jablonkagroup_ChemBench.txt
└── vincentkoc_tiny_qa_benchmark_pp.txt
```

---

## Known Issues

### 1. Generated Scripts Fail Execution
**Problem:** Claude generates scripts that assume:
- Dataset has `train` and `test` splits (many only have `train`)
- Specific column names (`text`, `label`) that don't exist
- Config names that are wrong (e.g., `classification-1` vs actual names)

**Solution needed:** Either:
- Improve prompt to generate more robust scripts
- Create a template that handles edge cases
- Have agents explore dataset structure first before generating code

### 2. Dataset Structure Varies Widely
**Examples of failures:**
```
KeyError: 'test'                    # No test split
ValueError: BuilderConfig 'classification-1' not found
KeyError: 'text'                    # Different column names
```

---

## Remaining Tasks for Handoff

### Priority 1: Fix Script Generation
- [ ] Update `command_generator.py` prompt to:
  - First explore dataset structure (`dataset.keys()`, `dataset['train'].features`)
  - Use `train_test_split` if no test split exists
  - Handle different column names dynamically

### Priority 2: Run Full Pipeline
- [ ] Generate scripts for all 167 datasets
- [ ] Execute and collect results
- [ ] Create summary report with accuracy metrics

### Priority 3: Add CFA Integration
- [ ] Modify generated scripts to include:
  - Multiple classical models (SVM, RF, XGB, MLP, AdaBoost)
  - Quantum models (VQC with PennyLane)
  - CFA ensemble methods (score avg, rank avg, diversity-weighted)
- [ ] Reference implementation: `quantumprep/project/phase2_classification/cfa_reference/cfa_simplified.py`

### Priority 4: Benchmark Comparison
- [ ] Compare results to known benchmarks
- [ ] Document which datasets CFA improves performance on

---

## How to Continue

### Quick Start
```bash
cd /home/seanpatten/projects/a/agent_spawner_test

# Generate more scripts
python command_generator.py -n 20 -p 5

# Try running them
python run_all.py

# Check failures
cat results/*_result.txt | grep -A5 "FAIL"
```

### Full Context
Read `CONTINUE_PROMPT.md` for:
- Project background (Quantum + Classical + CFA)
- CFA formulas (Equations 3-7 from ADMET paper)
- Reference implementations to study
- Expected outcomes

### Key Files in Parent Project
```
/home/seanpatten/projects/aWorktrees/quantumfusion-20260130-032056/
├── step_1/
│   ├── classify_wine.py           # Working CFA experiment
│   ├── results_report.md          # Results documentation
│   └── download_tiny_dataset.py   # Dataset downloader
└── quantumprep/project/phase2_classification/
    ├── classify.py                # Original 3-dataset experiment
    └── cfa_reference/
        └── cfa_simplified.py      # CFA implementation
```

---

## Command Reference

```bash
# List datasets
python agent_spawner.py --list

# Generate commands for N datasets with P parallel agents
python command_generator.py -n <N> -p <P>

# Run all generated scripts
python run_all.py

# Run single dataset with streaming
python agent_spawner.py <dataset_name>

# Run all datasets sequentially
python agent_spawner.py --all
```

---

## Metrics to Track

When running experiments, collect:
- **Individual model accuracy** (SVM, RF, XGB, MLP, VQC1, VQC2)
- **Individual model AUROC**
- **CFA ensemble accuracy** (all 4 methods)
- **Best single model vs best ensemble**
- **Diversity strength** per model
- **Performance strength** per model

---

*Report generated: 2026-01-30*
*Location: /home/seanpatten/projects/a/agent_spawner_test/*
