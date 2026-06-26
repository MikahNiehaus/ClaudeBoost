<!-- Source: github.com/TanStack/query/docs/framework\svelte\reference\functions\createInfiniteQuery.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: createInfiniteQuery
title: createInfiniteQuery
---

# Function: createInfiniteQuery()

```ts
function createInfiniteQuery<TQueryFnData, TError, TData, TQueryKey, TPageParam>(options, queryClient?): CreateInfiniteQueryResult<TData, TError>;
```

Defined in: [packages/svelte-query/src/createInfiniteQuery.ts:16](https://github.com/TanStack/query/blob/main/packages/svelte-query/src/createInfiniteQuery.ts#L16)

## Type Parameters

### TQueryFnData

`TQueryFnData`

### TError

`TError` = `Error`

### TData

`TData` = `InfiniteData`\<`TQueryFnData`, `unknown`\>

### TQueryKey

`TQueryKey` *extends* readonly `unknown`[] = readonly `unknown`[]

### TPageParam

`TPageParam` = `unknown`

## Parameters

### options

[`Accessor`](../type-aliases/Accessor.md)\<[`CreateInfiniteQueryOptions`](../type-aliases/CreateInfiniteQueryOptions.md)\<`TQueryFnData`, `TError`, `TData`, `TQueryKey`, `TPageParam`\>\>

### queryClient?

[`Accessor`](../type-aliases/Accessor.md)\<`QueryClient`\>

## Returns

[`CreateInfiniteQueryResult`](../type-aliases/CreateInfiniteQueryResult.md)\<`TData`, `TError`\>
