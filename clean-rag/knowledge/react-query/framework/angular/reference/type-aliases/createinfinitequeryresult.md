<!-- Source: github.com/TanStack/query/docs/framework\angular\reference\type-aliases\CreateInfiniteQueryResult.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: CreateInfiniteQueryResult
title: CreateInfiniteQueryResult
---

# Type Alias: CreateInfiniteQueryResult\<TData, TError\>

```ts
type CreateInfiniteQueryResult<TData, TError> = BaseQueryNarrowing<TData, TError> & MapToSignals<InfiniteQueryObserverResult<TData, TError>>;
```

Defined in: [types.ts:117](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/types.ts#L117)

## Type Parameters

### TData

`TData` = `unknown`

### TError

`TError` = `DefaultError`
