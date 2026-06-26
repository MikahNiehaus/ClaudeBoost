<!-- Source: github.com/TanStack/query/docs/framework\preact\guides\disabling-queries.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: disabling-queries
title: Disabling/Pausing Queries
ref: docs/framework/react/guides/disabling-queries.md
replace: { 'react-query': 'preact-query', 'React': 'Preact' }
---

[//]: # 'Example2'

```tsx
function Todos() {
  const [filter, setFilter] = useState('')

  const { data } = useQuery({
    queryKey: ['todos', filter],
    queryFn: () => fetchTodos(filter),
    // ⬇️ disabled as long as the filter is empty
    enabled: !!filter,
  })

  return (
    <div>
      // 🚀 applying the filter will enable and execute the query
      <FiltersForm onApply={setFilter} />
      {data && <TodosTable data={data} />}
    </div>
  )
}
```

[//]: # 'Example2'
[//]: # 'Example3'

```tsx
import { skipToken, useQuery } from '@tanstack/preact-query'

function Todos() {
  const [filter, setFilter] = useState<string | undefined>()

  const { data } = useQuery({
    queryKey: ['todos', filter],
    // ⬇️ disabled as long as the filter is undefined or empty
    queryFn: filter ? () => fetchTodos(filter) : skipToken,
  })

  return (
    <div>
      // 🚀 applying the filter will enable and execute the query
      <FiltersForm onApply={setFilter} />
      {data && <TodosTable data={data} />}
    </div>
  )
}
```

[//]: # 'Example3'
