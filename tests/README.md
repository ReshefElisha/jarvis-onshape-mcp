# Onshape MCP Server - Test Suite

Comprehensive unit test suite for the Onshape MCP server.

## Test Structure

```
tests/
├── conftest.py           # Shared fixtures and pytest configuration
├── api/                  # API layer tests
│   ├── test_client.py    # OnshapeClient HTTP operations
│   ├── test_partstudio.py # Part Studio manager tests
│   └── test_variables.py # Variable manager tests
└── builders/             # Builder pattern tests
    ├── test_sketch.py    # Sketch builder tests
    └── test_extrude.py   # Extrude builder tests
```

## Running Tests

### Quick Start

```bash
# Install dependencies
make install

# Run all tests
make test

# Run with coverage
make test-cov

# Run unit tests only
make test-unit
```

### Using pytest directly

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/api/test_client.py

# Run specific test class
pytest tests/api/test_client.py::TestOnshapeClient

# Run specific test method
pytest tests/api/test_client.py::TestOnshapeClient::test_get_request_success

# Run tests matching pattern
pytest -k "test_add_rectangle"

# Run with coverage
pytest --cov=onshape_mcp --cov-report=html
```

## Test Categories

Tests are marked with the following markers:

- `@pytest.mark.asyncio` - Async tests
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Slow running tests

### Run tests by category

```bash
# Run only async tests
pytest -m asyncio

# Skip slow tests
pytest -m "not slow"

# Run unit tests only
pytest -m unit
```

## Coverage Reports

### Generate HTML coverage report

```bash
make coverage-html
# Open htmlcov/index.html in browser
```

### Generate XML coverage report (for CI)

```bash
make coverage-xml
```

### Coverage thresholds

The test suite enforces a minimum coverage of **80%**. Tests will fail if coverage falls below this threshold.

## Writing Tests

### Test Structure

All tests follow the Arrange-Act-Assert (AAA) pattern:

```python
def test_example():
    # Arrange - Set up test data and mocks
    client = OnshapeClient(credentials)

    # Act - Execute the code being tested
    result = client.do_something()

    # Assert - Verify the results
    assert result == expected_value
```

### Using Fixtures

Common fixtures are defined in `conftest.py`:

```python
def test_with_fixtures(onshape_client, sample_document_ids):
    """Test using shared fixtures."""
    result = onshape_client.get_features(**sample_document_ids)
    assert result is not None
```

### Async Tests

Use `@pytest.mark.asyncio` for async tests:

```python
@pytest.mark.asyncio
async def test_async_operation(onshape_client):
    """Test async operation."""
    result = await onshape_client.get("/api/test")
    assert result["success"] is True
```

### Mocking HTTP Requests

Use the `mock_httpx_client` fixture for mocking HTTP responses:

```python
@pytest.mark.asyncio
async def test_api_call(onshape_client, mock_httpx_client):
    """Test API call with mocked response."""
    mock_response = Mock()
    mock_response.json.return_value = {"data": "test"}
    mock_httpx_client.get.return_value = mock_response

    result = await onshape_client.get("/api/endpoint")
    assert result["data"] == "test"
```

## Continuous Integration

Tests are designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    pip install -e ".[dev]"
    pytest --cov=onshape_mcp --cov-report=xml

- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

## Test Coverage by Module

| Module | Coverage | Tests |
|--------|----------|-------|
| api/client.py | ~95% | 15 tests |
| api/partstudio.py | ~90% | 9 tests |
| api/variables.py | ~90% | 12 tests |
| builders/sketch.py | ~95% | 20 tests |
| builders/extrude.py | ~95% | 18 tests |

## Troubleshooting

### Tests failing with import errors

```bash
# Ensure package is installed in editable mode
pip install -e .
```

### Coverage report not generating

```bash
# Clean cache and regenerate
make clean
pytest --cov=onshape_mcp --cov-report=html
```

### Async tests not running

```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio
```

## Best Practices

1. **Test isolation** - Each test should be independent
2. **Mock external dependencies** - Use fixtures for HTTP clients
3. **Descriptive names** - Test names should describe what they test
4. **One assertion per test** - Keep tests focused
5. **Arrange-Act-Assert** - Follow AAA pattern
6. **Edge cases** - Test boundary conditions and error cases
7. **Coverage** - Maintain 80%+ code coverage

## Adding New Tests

When adding new functionality:

1. Write tests first (TDD approach)
2. Create test file matching module name: `test_<module>.py`
3. Add fixtures to `conftest.py` if reusable
4. Update this README with new test information
5. Ensure coverage stays above 80%

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [coverage.py documentation](https://coverage.readthedocs.io/)
