<!-- Source: github.com/TanStack/query/docs/framework\solid\guides\window-focus-refetching.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: window-focus-refetching
title: Window Focus Refetching
ref: docs/framework/react/guides/window-focus-refetching.md
replace: { '@tanstack/react-query': '@tanstack/solid-query' }
---

[//]: # 'Example2'

```tsx
useQuery(() => ({
  queryKey: ['todos'],
  queryFn: fetchTodos,
  refetchOnWindowFocus: false,
}))
```

[//]: # 'Example2'
[//]: # 'ReactNative'
[//]: # 'ReactNative'
