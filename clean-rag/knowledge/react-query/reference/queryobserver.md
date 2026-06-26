<!-- Source: github.com/TanStack/query/docs/reference\QueryObserver.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: QueryObserver
title: QueryObserver
---

The `QueryObserver` can be used to observe and switch between queries.

```tsx
const observer = new QueryObserver(queryClient, { queryKey: ['posts'] })

const unsubscribe = observer.subscribe((result) => {
  console.log(result)
  unsubscribe()
})
```

**Options**

The options for the `QueryObserver` are exactly the same as those of [`useQuery`](../framework/react/reference/useQuery).
