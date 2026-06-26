<!-- Source: github.com/fastapi/fastapi/docs/en/docs/reference\uploadfile.md | Tier: A | Topic: fastapi | Fetched: 2026-06-26 -->

# `UploadFile` class

You can define *path operation function* parameters to be of the type `UploadFile` to receive files from the request.

You can import it directly from `fastapi`:

```python
from fastapi import UploadFile
```

::: fastapi.UploadFile
    options:
        members:
            - file
            - filename
            - size
            - headers
            - content_type
            - read
            - write
            - seek
            - close
