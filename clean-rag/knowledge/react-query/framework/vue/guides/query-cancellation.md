<!-- Source: github.com/TanStack/query/docs/framework\vue\guides\query-cancellation.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: query-cancellation
title: Query Cancellation
ref: docs/framework/react/guides/query-cancellation.md
---

[//]: # 'Example7'

```ts
const query = useQuery({
  queryKey: ['todos'],
  queryFn: async ({ signal }) => {
    const resp = await fetch('/todos', { signal })
    return resp.json()
  },
})

const queryClient = useQueryClient()

function onButtonClick() {
  queryClient.cancelQueries({ queryKey: ['todos'] })
}
```

[//]: # 'Example7'
