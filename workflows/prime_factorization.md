# Prime Factorization Program Workflow

This workflow creates, tests, debugs, and optimizes a prime factorization program.

## Step 1: Create the program

```bash
cat > prime_factor.py << 'EOF'
def factor(n):
    factors = []
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    if n > 1:
        factors.append(n)
    return factors

if __name__ == "__main__":
    import sys
    num = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    print(f"Prime factors of {num}: {factor(num)}")
EOF
```

## Step 2: Test the program

```bash
python3 prime_factor.py 100
python3 prime_factor.py 12345
python3 prime_factor.py 997
```

## Step 3: Create unit tests

```bash
cat > test_prime_factor.py << 'EOF'
from prime_factor import factor

def test_factor():
    assert factor(100) == [2, 2, 5, 5]
    assert factor(12) == [2, 2, 3]
    assert factor(13) == [13]
    assert factor(1) == []
    print("All tests passed!")

if __name__ == "__main__":
    test_factor()
EOF
```

## Step 4: Run tests

```bash
python3 test_prime_factor.py
```

## Step 5: Ask Claude to optimize it

```bash
claude --model sonnet --dangerously-skip-permissions "Review prime_factor.py and suggest optimizations for speed and brevity"
```

## Step 6: Apply optimizations and test again

```bash
python3 prime_factor.py 1000000007
python3 test_prime_factor.py
```

## Step 7: Done

```bash
echo "Workflow completed successfully!"
```
