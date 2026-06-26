<!-- Source: github.com/TanStack/query/docs/framework\angular\reference\type-aliases\UnusedSkipTokenInfiniteOptions.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: UnusedSkipTokenInfiniteOptions
title: UnusedSkipTokenInfiniteOptions
---

# Type Alias: UnusedSkipTokenInfiniteOptions\<TQueryFnData, TError, TData, TQueryKey, TPageParam\>

```ts
type UnusedSkipTokenInfiniteOptions<TQueryFnData, TError, TData, TQueryKey, TPageParam> = OmitKeyof<CreateInfiniteQueryOptions<TQueryFnData, TError, TData, TQueryKey, TPageParam>, "queryFn"> & object;
```

Defined in: [infinite-query-options.ts:34](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/infinite-query-options.ts#L34)

## Type Declaration

### queryFn?

```ts
optional queryFn: Exclude<CreateInfiniteQueryOptions<TQueryFnData, TError, TData, TQueryKey, TPageParam>["queryFn"], SkipToken | undefined>;
```

## Type Parameters

### TQueryFnData

`TQueryFnData`

### TError

`TError` = `DefaultError`

### TData

`TData` = `InfiniteData`\<`TQueryFnData`\>

### TQueryKey

`TQueryKey` *extends* `QueryKey` = `QueryKey`

### TPageParam

`TPageParam` = `unknown`
