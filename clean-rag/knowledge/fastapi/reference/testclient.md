<!-- Source: github.com/fastapi/fastapi/docs/en/docs/reference\testclient.md | Tier: A | Topic: fastapi | Fetched: 2026-06-26 -->

# Test Client - `TestClient`

You can use the `TestClient` class to test FastAPI applications without creating an actual HTTP and socket connection, just communicating directly with the FastAPI code.

Read more about it in the [FastAPI docs for Testing](https://fastapi.tiangolo.com/tutorial/testing/).

You can import it directly from `fastapi.testclient`:

```python
from fastapi.testclient import TestClient
```

::: fastapi.testclient.TestClient
