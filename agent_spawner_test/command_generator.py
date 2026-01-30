#!/usr/bin/env python3
"""
Command Generator - Spawns Claude agents in parallel to generate model training commands.
Saves commands to txt files in a results folder.
"""

import subprocess
import sys
import os
import csv
import json
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

RESULTS_DIR = Path(__file__).parent / "generated_commands"
DATASETS_FILE = Path(__file__).parent / "small_datasets.csv"
MAX_PARALLEL = 3
TIMEOUT_SECONDS = 60  # 1 min per dataset for command generation

def load_datasets(limit=10):
    """Load first N datasets from CSV."""
    datasets = []
    if not DATASETS_FILE.exists():
        print(f"[ERROR] {DATASETS_FILE} not found")
        return []

    with open(DATASETS_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('name', '')
            size = row.get('size_mb', '0')
            if name:
                datasets.append((name, size))
            if len(datasets) >= limit:
                break
    return datasets


def generate_commands_for_dataset(dataset_name, size_mb):
    """Spawn claude to generate commands for a dataset."""
    safe_name = dataset_name.replace("/", "_").replace("-", "_")
    output_file = RESULTS_DIR / f"{safe_name}.txt"

    prompt = f"""Generate a ROBUST Python script for HuggingFace dataset: {dataset_name}

CRITICAL: Many datasets have quirks. Your script MUST handle:
1. Datasets with multiple configs - pick the first available one
2. Datasets without 'train' split - use whatever split exists and train_test_split
3. Different column names - detect text/features and labels dynamically

Use this EXACT pattern:

```python
from datasets import load_dataset, get_dataset_config_names
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

# Step 1: Get available configs
try:
    configs = get_dataset_config_names("{dataset_name}")
    config = configs[0] if configs else None
except:
    config = None

# Step 2: Load dataset
try:
    if config:
        ds = load_dataset("{dataset_name}", config, trust_remote_code=True)
    else:
        ds = load_dataset("{dataset_name}", trust_remote_code=True)
except Exception as e:
    print(f"Load error: {{e}}")
    exit(1)

# Step 3: Get data from first available split
split_name = list(ds.keys())[0]
data = ds[split_name]
print(f"Using split: {{split_name}}, samples: {{len(data)}}")

# Step 4: Find features and labels (adapt column names)
cols = data.column_names
print(f"Columns: {{cols}}")

# Try common patterns for labels (case-insensitive)
label_col = None
label_patterns = ['label', 'labels', 'target', 'class', 'category', 'answer', 'answerkey', 'answers', 'y', 'output', 'response', 'choice']
for c in cols:
    if c.lower() in label_patterns:
        label_col = c
        break

# Try common patterns for features (case-insensitive)
feat_col = None
feat_patterns = ['text', 'question', 'questions', 'input', 'sentence', 'content', 'prompt', 'query', 'x', 'features', 'context', 'instruction']
for c in cols:
    if c.lower() in feat_patterns:
        feat_col = c
        break

if not label_col or not feat_col:
    print(f"Could not find suitable columns. Available: {{cols}}")
    # Try first string col as feature, first int/class col as label
    for c in cols:
        sample = data[0][c]
        if isinstance(sample, str) and feat_col is None:
            feat_col = c
        if isinstance(sample, (int, bool)) and label_col is None:
            label_col = c

if not label_col or not feat_col:
    print("Cannot identify feature/label columns")
    exit(1)

print(f"Using: features={{feat_col}}, labels={{label_col}}")

# Step 5: Prepare data
X_raw = [str(x) for x in data[feat_col]]
y = np.array(data[label_col])

# Handle multi-class labels
unique_labels = np.unique(y)
if len(unique_labels) > 10:
    print(f"Too many labels ({{len(unique_labels)}}), using first 2 classes")
    mask = np.isin(y, unique_labels[:2])
    X_raw = [X_raw[i] for i in range(len(X_raw)) if mask[i]]
    y = y[mask]

# Vectorize text
vectorizer = TfidfVectorizer(max_features=500)
X = vectorizer.fit_transform(X_raw).toarray()

# Train/test split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train and evaluate
clf = RandomForestClassifier(n_estimators=50, random_state=42)
clf.fit(X_train, y_train)
y_pred = clf.predict(X_test)
acc = accuracy_score(y_test, y_pred)
print(f"Accuracy: {{acc:.4f}}")
```

Adapt the template above for {dataset_name}. Output ONLY the Python code block.
"""

    print(f"[START] {dataset_name}", flush=True)

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            cwd=Path(__file__).parent,
        )

        output = result.stdout.strip()

        # Save to file
        with open(output_file, 'w') as f:
            f.write(f"# Dataset: {dataset_name}\n")
            f.write(f"# Size: {size_mb}MB\n\n")
            f.write(output)

        print(f"[DONE] {dataset_name} -> {output_file.name}", flush=True)
        return (dataset_name, "success", output_file)

    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] {dataset_name}", flush=True)
        return (dataset_name, "timeout", None)
    except Exception as e:
        print(f"[ERROR] {dataset_name}: {e}", flush=True)
        return (dataset_name, "error", str(e))


def run_parallel(datasets):
    """Run command generation in parallel."""
    RESULTS_DIR.mkdir(exist_ok=True)

    print(f"\n{'='*60}")
    print(f" GENERATING COMMANDS FOR {len(datasets)} DATASETS")
    print(f" Max parallel: {MAX_PARALLEL}")
    print(f" Output: {RESULTS_DIR}")
    print(f"{'='*60}\n")

    results = []

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
        futures = {
            executor.submit(generate_commands_for_dataset, name, size): name
            for name, size in datasets
        }

        for future in as_completed(futures):
            dataset = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"[EXCEPTION] {dataset}: {e}")
                results.append((dataset, "exception", str(e)))

    # Summary
    print(f"\n{'='*60}")
    print(" SUMMARY")
    print(f"{'='*60}")

    success = sum(1 for r in results if r[1] == "success")
    print(f"Success: {success}/{len(results)}")
    print(f"Files saved to: {RESULTS_DIR}")

    # List generated files
    print(f"\nGenerated files:")
    for f in sorted(RESULTS_DIR.glob("*.txt")):
        print(f"  - {f.name}")

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--num", type=int, default=5, help="Number of datasets")
    parser.add_argument("-p", "--parallel", type=int, default=3, help="Max parallel agents")
    args = parser.parse_args()

    global MAX_PARALLEL
    MAX_PARALLEL = args.parallel

    datasets = load_datasets(limit=args.num)
    if not datasets:
        print("No datasets found")
        return

    print(f"Loaded {len(datasets)} datasets")
    run_parallel(datasets)


if __name__ == "__main__":
    main()
