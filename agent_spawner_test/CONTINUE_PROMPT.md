# Quantum-Classical Fusion Analysis: Continuation Prompt

## Project Overview

This project compares **Quantum Machine Learning (QML)** models against **Classical ML** models, then ensembles them using **Combinatorial Fusion Analysis (CFA)** - a technique from Dr. D. Frank Hsu's research that was successfully applied to ADMET drug discovery benchmarks.

### Goal
1. Select a dataset from HuggingFace
2. Train classical models (XGBoost, Random Forest, SVM, AdaBoost, MLP)
3. Train quantum models (Variational Quantum Classifiers using PennyLane)
4. Apply CFA ensemble methods (score avg, rank avg, diversity-weighted, performance-weighted)
5. Compare results and document findings

---

## Materials to Read First

### Required Reading (in order)
1. **CFA Reference Implementation**
   ```
   quantumprep/project/phase2_classification/cfa_reference/cfa_simplified.py
   ```
   - Core CFA algorithms: diversity strength, performance strength, combination methods
   - Equations 3-7 from the ADMET paper implemented

2. **ADMET Paper (PDF)**
   ```
   step_1/cfa_materials/admet/enhancing-admet-property-models-performance-through-combinatorial-fusion-analysis (1).pdf
   ```
   - Key concepts: cognitive diversity, rank-score functions, when rank > score combination
   - Results: CFA achieved #1 on 4/22 TDC datasets, top-6 on 16/22

3. **Existing Experiments**
   ```
   quantumprep/project/phase2_classification/classify.py  # Original 3-dataset experiment
   step_1/classify_wine.py                                 # Wine dataset experiment
   step_1/results_report.md                                # Results summary
   ```

4. **Dataset Lists**
   ```
   step_1/small_datasets.csv      # 169 tiny datasets with sizes
   datasets.tsv                   # Larger dataset catalog
   benchmark_datasets.tsv         # Benchmark datasets
   ```

5. **Quantum Model References**
   ```
   step_1/repos/working/Var-QuantumCircuits-DeepRL/    # VQC examples
   step_1/repos/working/Quantum_Long_Short_Term_Memory/ # QLSTM
   ```

---

## How to Download Datasets

### Using the Dataset Downloader

```bash
cd step_1
uv run --with datasets --with pandas --with pyarrow python download_tiny_dataset.py
```

This script:
- Tries datasets from smallest to largest (0.1MB - 0.7MB)
- Saves to `step_1/data/` as parquet files
- Shows preview of the data

### Manual Download (specific dataset)

```python
from datasets import load_dataset

# Example: ChemBench (chemistry, similar to ADMET)
ds = load_dataset("jablonkagroup/ChemBench")

# Example: Health benchmarks
ds = load_dataset("yesilhealth/Health_Benchmarks")

# Example: ToxiMol (toxicity prediction - very relevant!)
ds = load_dataset("DeepYoke/ToxiMol-benchmark")
```

### Recommended Datasets for This Project

| Dataset | Size | Why Good for CFA |
|---------|------|------------------|
| `jablonkagroup/ChemBench` | 0.7MB | Chemistry - similar to ADMET |
| `DeepYoke/ToxiMol-benchmark` | 19.5MB | Toxicity prediction |
| `yesilhealth/Health_Benchmarks` | 1.4MB | Medical classification |
| `google/simpleqa-verified` | 0.3MB | Simple QA benchmark |
| `vincentkoc/tiny_qa_benchmark_pp` | 0.2MB | Tiny, good for testing |

---

## Datasets Already Completed (DO NOT REPEAT)

| Dataset | Location | Status |
|---------|----------|--------|
| moons (sklearn) | classify.py | Done |
| iris (sklearn) | classify.py | Done |
| breast_cancer (sklearn) | classify.py | Done |
| wine (sklearn) | classify_wine.py | Done |
| AgentsNet | step_1/data/ | Downloaded only |

---

## Your Task

### Step 1: Select a New Dataset
Pick ONE dataset from `small_datasets.csv` that:
- Is NOT in the "Already Completed" list above
- Has a classification task (binary or multi-class)
- Is small enough for quantum simulation (<50MB recommended)

**Good choices:** ChemBench, Health_Benchmarks, ToxiMol-benchmark, simpleqa-verified

### Step 2: Download and Explore
```bash
# Modify download_tiny_dataset.py or use:
uv run --with datasets python -c "
from datasets import load_dataset
ds = load_dataset('YOUR_DATASET_NAME')
print(ds)
print(ds['train'][0])
"
```

### Step 3: Create Experiment Script
Create `step_1/classify_<dataset_name>.py` following the template in `classify_wine.py`:

```python
# Required structure:
1. Load and preprocess data (StandardScaler, train/test split)
2. Train 5 classical models: XGB, RF, SVM, ADB, MLP
3. Train 2 quantum models: VQC (4 qubits, 1-2 layers)
4. Compute CFA metrics:
   - Diversity strength (Eq 4)
   - Performance strength (AUROC)
5. Apply 4 combination methods:
   - Average score
   - Average rank
   - Diversity-weighted
   - Performance-weighted
6. Print results table
```

### Step 4: Run and Debug
```bash
cd step_1
uv run --with pennylane --with xgboost --with scikit-learn --with datasets python classify_<name>.py
```

Common issues:
- **ArrayBox error in quantum training**: Use explicit loop instead of np.mean() in cost function
- **Dataset format**: Convert HuggingFace dataset to numpy arrays
- **Multi-class**: Convert to binary (one-vs-rest) for quantum compatibility

### Step 5: Document Results
Update `results_report.md` with:
- Dataset info (size, features, task)
- Individual model accuracies
- CFA ensemble results
- Comparison to any known benchmarks
- Key findings (did CFA improve over best single model?)

---

## Key CFA Formulas to Implement

### Cognitive Diversity (Eq 3)
```python
cd(A, B) = sqrt(sum((f_A(i) - f_B(i))^2) / n)
```
Where f_A, f_B are normalized rank-score functions.

### Diversity Strength (Eq 4)
```python
ds(A) = mean([cd(A, B) for B in other_models])
```

### Combination Methods (Eq 5-7)
```python
# Average
combined = mean([scores[m] for m in models])

# Diversity-weighted
combined = sum(scores[m] * ds[m]) / sum(ds.values())

# Performance-weighted
combined = sum(scores[m] * perf[m]) / sum(perf.values())
```

---

## Expected Outcomes

Based on the ADMET paper and our experiments:

1. **Classical models will likely outperform quantum** on small datasets (expected)
2. **CFA ensemble should match or beat best single model**
3. **Diversity-weighted may help** when models have different strengths
4. **Quantum models provide diversity** even if accuracy is lower

---

## File Structure

```
step_1/
├── classify_wine.py          # Wine experiment (DONE)
├── classify_<new>.py         # YOUR NEW EXPERIMENT
├── download_tiny_dataset.py  # Dataset downloader
├── results_report.md         # Results documentation
├── small_datasets.csv        # Dataset list
├── data/                     # Downloaded datasets
│   └── disco-eth_AgentsNet_train.parquet
├── repos/working/            # Reference quantum implementations
└── cfa_materials/            # CFA papers and references
```

---

## Commit Your Work

When done:
```bash
git add step_1/classify_<name>.py step_1/data/
git commit -m "Add CFA experiment: <dataset_name>

- Trained 5 classical + 2 quantum models
- Applied CFA ensemble methods
- Results: [brief summary]

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

**Do NOT push to main** - keep on this worktree branch.
