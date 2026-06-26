<!-- Source: github.com/TanStack/query/docs/framework\preact\reference\type-aliases\UseSuspenseQueryResult.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: UseSuspenseQueryResult
title: UseSuspenseQueryResult
---

# Type Alias: UseSuspenseQueryResult\<TData, TError\>

```ts
type UseSuspenseQueryResult<TData, TError> = DistributiveOmit<DefinedQueryObserverResult<TData, TError>, "isPlaceholderData" | "promise">;
```

Defined in: [preact-query/src/types.ts:160](https://github.com/theVedanta/query/blob/main/packages/preact-query/src/types.ts#L160)

## Type Parameters

### TData

`TData` = `unknown`

### TError

`TError` = `DefaultError`
