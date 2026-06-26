<!-- Source: github.com/TanStack/query/docs/framework\react\reference\infiniteQueryOptions.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: infiniteQueryOptions
title: infiniteQueryOptions
---

```tsx
infiniteQueryOptions({
  queryKey,
  ...options,
})
```

**Options**

You can generally pass everything to `infiniteQueryOptions` that you can also pass to [`useInfiniteQuery`](./useInfiniteQuery.md). Some options will have no effect when then forwarded to a function like `queryClient.prefetchInfiniteQuery`, but TypeScript will still be fine with those excess properties.

- `queryKey: QueryKey`
  - **Required**
  - The query key to generate options for.

See [useInfiniteQuery](./useInfiniteQuery.md) for more information.
