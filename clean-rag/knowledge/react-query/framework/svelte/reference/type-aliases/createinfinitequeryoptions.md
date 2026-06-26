<!-- Source: github.com/TanStack/query/docs/framework\svelte\reference\type-aliases\CreateInfiniteQueryOptions.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: CreateInfiniteQueryOptions
title: CreateInfiniteQueryOptions
---

# Type Alias: CreateInfiniteQueryOptions\<TQueryFnData, TError, TData, TQueryKey, TPageParam\>

```ts
type CreateInfiniteQueryOptions<TQueryFnData, TError, TData, TQueryKey, TPageParam> = InfiniteQueryObserverOptions<TQueryFnData, TError, TData, TQueryKey, TPageParam>;
```

Defined in: [packages/svelte-query/src/types.ts:53](https://github.com/TanStack/query/blob/main/packages/svelte-query/src/types.ts#L53)

Options for createInfiniteQuery

## Type Parameters

### TQueryFnData

`TQueryFnData` = `unknown`

### TError

`TError` = `DefaultError`

### TData

`TData` = `TQueryFnData`

### TQueryKey

`TQueryKey` *extends* `QueryKey` = `QueryKey`

### TPageParam

`TPageParam` = `unknown`
