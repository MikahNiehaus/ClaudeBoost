<!-- Source: github.com/TanStack/query/docs/framework\react\reference\QueryErrorResetBoundary.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: QueryErrorResetBoundary
title: QueryErrorResetBoundary
---

When using **suspense** or **throwOnError** in your queries, you need a way to let queries know that you want to try again when re-rendering after some error occurred. With the `QueryErrorResetBoundary` component you can reset any query errors within the boundaries of the component.

```tsx
import { QueryErrorResetBoundary } from '@tanstack/react-query'
import { ErrorBoundary } from 'react-error-boundary'

const App = () => (
  <QueryErrorResetBoundary>
    {({ reset }) => (
      <ErrorBoundary
        onReset={reset}
        fallbackRender={({ resetErrorBoundary }) => (
          <div>
            There was an error!
            <Button onClick={() => resetErrorBoundary()}>Try again</Button>
          </div>
        )}
      >
        <Page />
      </ErrorBoundary>
    )}
  </QueryErrorResetBoundary>
)
```
