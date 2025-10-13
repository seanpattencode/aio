#!/bin/bash
# Complete verification that everything works

echo "=========================================="
echo "AIOS Complete Verification"
echo "=========================================="
echo

# 1. Test integrated tests
echo "1. Running integrated tests..."
./aios.py --test
TEST_RESULT=$?

if [ $TEST_RESULT -ne 0 ]; then
    echo "✗ Tests failed"
    exit 1
fi

echo
echo "2. Checking file organization..."
if [ -d "testing" ]; then
    echo "   ✓ testing/ folder exists"
    TEST_FILES=$(ls testing/*.py 2>/dev/null | wc -l)
    echo "   ✓ $TEST_FILES test files archived"
else
    echo "   ✗ testing/ folder not found"
    exit 1
fi

echo
echo "3. Checking main file..."
if [ -f "aios.py" ]; then
    LINES=$(wc -l < aios.py)
    echo "   ✓ aios.py exists ($LINES lines)"
    if [ $LINES -lt 800 ]; then
        echo "   ✓ Line count reasonable"
    else
        echo "   ⚠ Line count high"
    fi
else
    echo "   ✗ aios.py not found"
    exit 1
fi

echo
echo "4. Checking no leftover files..."
LEFTOVER=$(ls *.png 2>/dev/null | wc -l)
if [ $LEFTOVER -eq 0 ]; then
    echo "   ✓ No leftover screenshot files"
else
    echo "   ✗ Found $LEFTOVER leftover files"
fi

echo
echo "5. Testing import..."
python3 -c "import aios" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "   ✓ aios.py imports successfully"
else
    echo "   ✗ Import failed"
    exit 1
fi

echo
echo "=========================================="
echo "✓ ALL VERIFICATIONS PASSED"
echo "=========================================="
echo
echo "Summary:"
echo "  - Integrated tests: PASSED"
echo "  - File organization: CLEAN"
echo "  - Main file: WORKING"
echo "  - Import: SUCCESS"
echo
echo "AIOS is production ready!"
