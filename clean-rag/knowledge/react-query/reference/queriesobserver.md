<!-- Source: github.com/TanStack/query/docs/reference\QueriesObserver.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: QueriesObserver
title: QueriesObserver
---

## `QueriesObserver`

The `QueriesObserver` can be used to observe multiple queries.

```tsx
const observer = new QueriesObserver(queryClient, [
  { queryKey: ['post', 1], queryFn: fetchPost },
  { queryKey: ['post', 2], queryFn: fetchPost },
])

const unsubscribe = observer.subscribe((result) => {
  console.log(result)
  unsubscribe()
})
```

**Options**

The options for the `QueriesObserver` are exactly the same as those of [`useQueries`](../framework/react/reference/useQueries).
