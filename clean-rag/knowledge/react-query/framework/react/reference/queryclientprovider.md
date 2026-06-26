<!-- Source: github.com/TanStack/query/docs/framework\react\reference\QueryClientProvider.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: QueryClientProvider
title: QueryClientProvider
---

Use the `QueryClientProvider` component to connect and provide a `QueryClient` to your application:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient()

function App() {
  return <QueryClientProvider client={queryClient}>...</QueryClientProvider>
}
```

**Options**

- `client: QueryClient`
  - **Required**
  - the QueryClient instance to provide
