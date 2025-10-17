# Testing Guide - Onshape MCP Server

## Quick Reference

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific test file
pytest tests/api/test_client.py

# Run in verbose mode
pytest -v

# Run and show print statements
pytest -s

# Run last failed tests
pytest --lf

# Run with specific markers
pytest -m asyncio
```

### Common Make Commands

```bash
make test          # Run all tests
make test-cov      # Run tests with coverage report
make test-unit     # Run unit tests only
make coverage-html # Generate HTML coverage report
make lint          # Run code linting
make format        # Format code
make check-all     # Run all checks (lint, type, test)
make clean         # Clean build artifacts
```

## Test Organization

### Directory Structure

```
tests/
├── conftest.py              # Shared fixtures
├── README.md                # Test documentation
├── api/
│   ├── test_client.py       # HTTP client tests (15 tests)
│   ├── test_partstudio.py   # Part Studio tests (9 tests)
│   └── test_variables.py    # Variable manager tests (12 tests)
└── builders/
    ├── test_sketch.py       # Sketch builder tests (20 tests)
    └── test_extrude.py      # Extrude builder tests (18 tests)

Total: 74 unit tests
```

## Test Coverage Goals

| Component | Target | Current |
|-----------|--------|---------|
| Overall | 80% | TBD |
| API Client | 90% | TBD |
| Part Studio Manager | 85% | TBD |
| Variable Manager | 85% | TBD |
| Sketch Builder | 90% | TBD |
| Extrude Builder | 90% | TBD |

## Writing Tests

### Test Naming Convention

```python
# Format: test_<function>_<scenario>
def test_add_rectangle_basic():
    """Test adding a basic rectangle."""
    pass

def test_add_rectangle_with_variables():
    """Test adding rectangle with width and height variables."""
    pass
```

### Using Fixtures

```python
@pytest.mark.asyncio
async def test_get_features(onshape_client, sample_document_ids):
    """Use fixtures from conftest.py"""
    result = await client.get_features(**sample_document_ids)
    assert result is not None
```

### Testing Async Code

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """Test async functions."""
    result = await some_async_function()
    assert result is not None
```

### Mocking HTTP Requests

```python
from unittest.mock import Mock, AsyncMock

@pytest.mark.asyncio
async def test_api_call(onshape_client, mock_httpx_client):
    """Mock HTTP responses."""
    mock_response = Mock()
    mock_response.json.return_value = {"success": True}
    mock_httpx_client.get.return_value = mock_response

    result = await onshape_client.get("/api/test")
    assert result["success"] is True
```

### Testing Error Handling

```python
import pytest

def test_error_handling():
    """Test that errors are raised correctly."""
    with pytest.raises(ValueError) as exc_info:
        raise_error_function()

    assert "error message" in str(exc_info.value)
```

## Available Fixtures

### From conftest.py

- `mock_credentials` - Mock OnshapeCredentials
- `mock_httpx_client` - Mock httpx AsyncClient
- `onshape_client` - Configured OnshapeClient with mocked HTTP
- `sample_document_ids` - Sample document/workspace/element IDs
- `sample_feature_response` - Sample feature API response
- `sample_variables` - Sample variable data

### Creating Custom Fixtures

```python
@pytest.fixture
def custom_fixture():
    """Create a custom fixture."""
    return {"data": "test"}

def test_with_custom_fixture(custom_fixture):
    """Use custom fixture."""
    assert custom_fixture["data"] == "test"
```

## Continuous Integration

Tests run automatically on:
- Push to main/develop branches
- Pull requests to main/develop
- Multiple Python versions (3.10, 3.11, 3.12)
- Multiple OS (Ubuntu, macOS, Windows)

### CI Workflow

1. Checkout code
2. Set up Python environment
3. Install dependencies
4. Run linters (ruff)
5. Run type checker (mypy)
6. Run tests with coverage
7. Upload coverage to Codecov
8. Check coverage threshold (80%)

## Debugging Tests

### Run with debugger

```bash
# Use pytest with pdb
pytest --pdb

# Drop into debugger on first failure
pytest -x --pdb

# Use ipdb (if installed)
pytest --pdb --pdbcls=IPython.terminal.debugger:Pdb
```

### Show more output

```bash
# Show print statements
pytest -s

# Show local variables on failure
pytest --showlocals

# Show full traceback
pytest --tb=long
```

### Run specific tests

```bash
# Run one test
pytest tests/api/test_client.py::TestOnshapeClient::test_get_request_success

# Run tests matching pattern
pytest -k "test_add"

# Run tests by marker
pytest -m "not slow"
```

## Test Markers

```python
@pytest.mark.asyncio      # Async test
@pytest.mark.unit         # Unit test
@pytest.mark.integration  # Integration test
@pytest.mark.slow         # Slow running test
```

## Coverage Analysis

### Generate reports

```bash
# Terminal report
pytest --cov=onshape_mcp --cov-report=term-missing

# HTML report
pytest --cov=onshape_mcp --cov-report=html
open htmlcov/index.html

# XML report (for CI)
pytest --cov=onshape_mcp --cov-report=xml
```

### Coverage configuration

Coverage is configured in:
- `pyproject.toml` - [tool.coverage.*]
- `.coveragerc` - Coverage.py settings
- `pytest.ini` - Pytest coverage options

## Best Practices

1. **One test, one assertion** - Keep tests focused
2. **Descriptive names** - Test names should explain what they test
3. **AAA pattern** - Arrange, Act, Assert
4. **Test edge cases** - Not just happy path
5. **Mock external dependencies** - Don't make real API calls
6. **Isolate tests** - Each test should be independent
7. **Fast tests** - Unit tests should run quickly
8. **Maintain coverage** - Keep above 80%

## Troubleshooting

### Import errors

```bash
# Install package in editable mode
pip install -e .
```

### Async tests not running

```bash
# Install pytest-asyncio
pip install pytest-asyncio
```

### Coverage not including files

```bash
# Clean and regenerate
make clean
pytest --cov=onshape_mcp --cov-report=html
```

### Tests passing locally but failing in CI

- Check Python version compatibility
- Check OS-specific path issues
- Ensure all dependencies in pyproject.toml

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [coverage.py](https://coverage.readthedocs.io/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
