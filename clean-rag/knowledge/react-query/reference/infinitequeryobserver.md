<!-- Source: github.com/TanStack/query/docs/reference\InfiniteQueryObserver.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: InfiniteQueryObserver
title: InfiniteQueryObserver
---

## `InfiniteQueryObserver`

The `InfiniteQueryObserver` can be used to observe and switch between infinite queries.

```tsx
const observer = new InfiniteQueryObserver(queryClient, {
  queryKey: ['posts'],
  queryFn: fetchPosts,
  getNextPageParam: (lastPage, allPages) => lastPage.nextCursor,
  getPreviousPageParam: (firstPage, allPages) => firstPage.prevCursor,
})

const unsubscribe = observer.subscribe((result) => {
  console.log(result)
  unsubscribe()
})
```

**Options**

The options for the `InfiniteQueryObserver` are exactly the same as those of [`useInfiniteQuery`](../framework/react/reference/useInfiniteQuery).
