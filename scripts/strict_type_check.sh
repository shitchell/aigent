#!/bin/bash
# Ultra-strict type checking script for Aigent
# This will make the strictest statically-typed language developer proud

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

echo "🔍 Aigent Ultra-Strict Type & Docstring Checker"
echo "================================================"
echo "Religious-level type checking and documentation enforcement"
echo ""

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ] || [ ! -d "src" ]; then
    echo -e "${RED}Error: Must run from project root directory${NC}"
    exit 1
fi

# Parse arguments
FIX_IMPORTS=false
FIX_FORMAT=false
VERBOSE=false
CHECK_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --fix)
            FIX_IMPORTS=true
            FIX_FORMAT=true
            shift
            ;;
        --fix-imports)
            FIX_IMPORTS=true
            shift
            ;;
        --fix-format)
            FIX_FORMAT=true
            shift
            ;;
        --check-only)
            CHECK_ONLY=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --fix           Auto-fix imports and formatting"
            echo "  --fix-imports   Auto-fix import sorting only"
            echo "  --fix-format    Auto-fix code formatting only"
            echo "  --check-only    Only run checks, skip fixes"
            echo "  -v, --verbose   Show detailed output"
            echo "  -h, --help      Show this help message"
            echo ""
            echo "This script enforces:"
            echo "  - Complete type annotations on EVERYTHING"
            echo "  - Google-style docstrings with Args/Returns/Raises"
            echo "  - No untyped functions or variables"
            echo "  - No implicit Any types"
            echo "  - No missing return type hints"
            echo "  - Proper import sorting"
            echo "  - Consistent code formatting"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Track overall status
OVERALL_STATUS=0

# Function to run a check and report results
run_check() {
    local name=$1
    local cmd=$2
    local fix_cmd=$3
    local can_fix=$4

    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}Running: ${name}${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if [ "$VERBOSE" = true ]; then
        eval $cmd
        local status=$?
    else
        eval $cmd > /tmp/type_check_output.txt 2>&1
        local status=$?
        if [ $status -ne 0 ]; then
            cat /tmp/type_check_output.txt
        fi
    fi

    if [ $status -eq 0 ]; then
        echo -e "${GREEN}✓ ${name} passed${NC}"
    else
        echo -e "${RED}✗ ${name} failed${NC}"
        OVERALL_STATUS=1

        if [ "$can_fix" = true ] && [ "$CHECK_ONLY" = false ]; then
            if [ "$FIX_IMPORTS" = true ] || [ "$FIX_FORMAT" = true ]; then
                echo -e "${YELLOW}  Attempting auto-fix...${NC}"
                eval $fix_cmd
                echo -e "${GREEN}  Auto-fix applied. Re-run to verify.${NC}"
            else
                echo -e "${YELLOW}  Run with --fix to auto-fix some issues${NC}"
            fi
        fi
    fi
    echo ""
}

# Install dependencies if needed
echo -e "${MAGENTA}Checking dependencies...${NC}"
if ! python -m mypy --version > /dev/null 2>&1; then
    echo -e "${YELLOW}Installing type checking dependencies...${NC}"
    pip install -e ".[dev]" > /dev/null 2>&1
fi

# Create py.typed marker file if it doesn't exist
if [ ! -f "src/aigent/py.typed" ]; then
    echo -e "${YELLOW}Creating py.typed marker for PEP 561 compliance...${NC}"
    touch src/aigent/py.typed
fi

# 1. Import sorting with isort
if [ "$CHECK_ONLY" = false ]; then
    run_check \
        "Import Sorting (isort)" \
        "python -m isort src/ --check-only --diff" \
        "python -m isort src/" \
        true
fi

# 2. Code formatting with black
if [ "$CHECK_ONLY" = false ]; then
    run_check \
        "Code Formatting (black)" \
        "python -m black src/ --check" \
        "python -m black src/" \
        true
fi

# 3. Type checking with mypy (THE BIG ONE)
echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${MAGENTA}🔥 ULTRA-STRICT TYPE CHECKING WITH MYPY 🔥${NC}"
echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Run mypy with all our strict settings from pyproject.toml
if [ "$VERBOSE" = true ]; then
    python -m mypy src/aigent --config-file pyproject.toml
    MYPY_STATUS=$?
else
    python -m mypy src/aigent --config-file pyproject.toml > /tmp/mypy_output.txt 2>&1
    MYPY_STATUS=$?

    if [ $MYPY_STATUS -ne 0 ]; then
        echo -e "${RED}Type checking failed! Issues found:${NC}"
        echo ""

        # Parse and format mypy output for better readability
        python3 -c "
import re
import sys

with open('/tmp/mypy_output.txt', 'r') as f:
    content = f.read()

# Group errors by file
files = {}
for line in content.split('\n'):
    if not line.strip():
        continue
    if ': error:' in line or ': note:' in line:
        match = re.match(r'(.*?):(\d+):(\d+): (error|note): (.*?) \[(.*?)\]', line)
        if match:
            filepath, line_num, col, severity, message, code = match.groups()
            if filepath not in files:
                files[filepath] = []
            files[filepath].append({
                'line': int(line_num),
                'col': int(col),
                'severity': severity,
                'message': message,
                'code': code
            })

# Print formatted output
for filepath, errors in sorted(files.items()):
    print(f'\033[1;35m{filepath}\033[0m')
    for error in sorted(errors, key=lambda x: x['line']):
        color = '\033[0;31m' if error['severity'] == 'error' else '\033[0;33m'
        print(f'  {color}Line {error[\"line\"]}, Col {error[\"col\"]}: [{error[\"code\"]}]\033[0m')
        print(f'    {error[\"message\"]}')
    print()

# Print summary
error_count = sum(1 for errors in files.values() for e in errors if e['severity'] == 'error')
note_count = sum(1 for errors in files.values() for e in errors if e['severity'] == 'note')
print(f'\033[1;31mFound {error_count} errors and {note_count} notes in {len(files)} files\033[0m')
"
        echo ""
        echo -e "${YELLOW}Common fixes:${NC}"
        echo "  - Add type hints to all function parameters and returns"
        echo "  - Use 'Optional[Type]' instead of 'Type = None'"
        echo "  - Add '-> None' for functions that don't return anything"
        echo "  - Use 'List[Type]' instead of bare 'list'"
        echo "  - Use 'Dict[KeyType, ValueType]' instead of bare 'dict'"
        echo "  - Import types from 'typing' module"
        OVERALL_STATUS=1
    else
        echo -e "${GREEN}✓ Type checking passed - ALL types are properly annotated!${NC}"
    fi
fi
echo ""

# 4. Docstring checking with pydocstyle
echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${MAGENTA}📚 DOCSTRING ENFORCEMENT (Google Style) 📚${NC}"
echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ "$VERBOSE" = true ]; then
    python -m pydocstyle src/aigent --config=pyproject.toml
    DOCSTRING_STATUS=$?
else
    python -m pydocstyle src/aigent --config=pyproject.toml > /tmp/docstring_output.txt 2>&1
    DOCSTRING_STATUS=$?

    if [ $DOCSTRING_STATUS -ne 0 ]; then
        echo -e "${RED}Docstring issues found:${NC}"
        echo ""
        # Show first 20 issues
        head -n 20 /tmp/docstring_output.txt

        # Count total issues
        ISSUE_COUNT=$(grep -c ":" /tmp/docstring_output.txt || echo "0")
        if [ $ISSUE_COUNT -gt 20 ]; then
            echo ""
            echo -e "${YELLOW}... and $(($ISSUE_COUNT - 20)) more issues${NC}"
        fi

        echo ""
        echo -e "${YELLOW}Required docstring format:${NC}"
        echo '"""'
        echo "One-line summary of what this does."
        echo ""
        echo "Longer description if needed."
        echo ""
        echo "Args:"
        echo "    param1: Description of param1."
        echo "    param2: Description of param2."
        echo ""
        echo "Returns:"
        echo "    Description of return value."
        echo ""
        echo "Raises:"
        echo "    ValueError: When invalid value provided."
        echo '"""'
        OVERALL_STATUS=1
    else
        echo -e "${GREEN}✓ All docstrings present and properly formatted!${NC}"
    fi
fi
echo ""

# 5. Generate type coverage report
echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${MAGENTA}📊 TYPE COVERAGE REPORT 📊${NC}"
echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Count typed vs untyped lines
python3 -c "
import ast
import sys
from pathlib import Path

typed_funcs = 0
untyped_funcs = 0
typed_args = 0
untyped_args = 0

for py_file in Path('src').rglob('*.py'):
    try:
        with open(py_file, 'r') as f:
            tree = ast.parse(f.read(), filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check return type
                if node.returns:
                    typed_funcs += 1
                else:
                    untyped_funcs += 1

                # Check arguments
                for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                    if arg.annotation:
                        typed_args += 1
                    else:
                        untyped_args += 1
    except:
        continue

total_funcs = typed_funcs + untyped_funcs
total_args = typed_args + untyped_args

if total_funcs > 0:
    func_coverage = (typed_funcs / total_funcs) * 100
    print(f'Function return types: {typed_funcs}/{total_funcs} ({func_coverage:.1f}% coverage)')
else:
    print('No functions found')

if total_args > 0:
    arg_coverage = (typed_args / total_args) * 100
    print(f'Function arguments: {typed_args}/{total_args} ({arg_coverage:.1f}% coverage)')
else:
    print('No function arguments found')

if total_funcs > 0 and func_coverage == 100 and arg_coverage == 100:
    print('')
    print('\033[1;32m🎉 PERFECT TYPE COVERAGE! 100% typed! 🎉\033[0m')
elif total_funcs > 0 and func_coverage >= 95 and arg_coverage >= 95:
    print('')
    print('\033[1;33m⚠️  Almost there! >95% type coverage\033[0m')
elif total_funcs > 0:
    print('')
    print('\033[1;31m❌ Need more type hints! Target: 100% coverage\033[0m')
"
echo ""

# Final summary
echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ $OVERALL_STATUS -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED! Your code would make a Rust developer cry tears of joy! 🦀${NC}"
    echo -e "${GREEN}   - Every function is typed${NC}"
    echo -e "${GREEN}   - Every variable has type hints${NC}"
    echo -e "${GREEN}   - Every function has proper docstrings${NC}"
    echo -e "${GREEN}   - No implicit Any types${NC}"
    echo -e "${GREEN}   - Code is perfectly formatted${NC}"
else
    echo -e "${RED}❌ CHECKS FAILED - Your code needs more discipline!${NC}"
    echo ""
    echo -e "${YELLOW}To achieve type nirvana:${NC}"
    echo "  1. Add type hints to ALL functions: def func(x: int) -> str:"
    echo "  2. Add Google-style docstrings to ALL functions/classes/modules"
    echo "  3. Import types from 'typing' module (List, Dict, Optional, etc.)"
    echo "  4. Run with --fix to auto-fix formatting issues"
    echo "  5. Use 'mypy --strict' locally for immediate feedback"
    echo ""
    echo -e "${YELLOW}Remember: In the church of static typing, there is no 'Any'!${NC}"
fi
echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Clean up temp files
rm -f /tmp/type_check_output.txt /tmp/mypy_output.txt /tmp/docstring_output.txt

exit $OVERALL_STATUS