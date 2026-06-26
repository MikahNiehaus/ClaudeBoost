<!-- Source: github.com/TanStack/query/docs/framework\angular\reference\type-aliases\DefinedInitialDataInfiniteOptions.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: DefinedInitialDataInfiniteOptions
title: DefinedInitialDataInfiniteOptions
---

# Type Alias: DefinedInitialDataInfiniteOptions\<TQueryFnData, TError, TData, TQueryKey, TPageParam\>

```ts
type DefinedInitialDataInfiniteOptions<TQueryFnData, TError, TData, TQueryKey, TPageParam> = CreateInfiniteQueryOptions<TQueryFnData, TError, TData, TQueryKey, TPageParam> & object;
```

Defined in: [infinite-query-options.ts:62](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/infinite-query-options.ts#L62)

## Type Declaration

### initialData

```ts
initialData: 
  | NonUndefinedGuard<InfiniteData<TQueryFnData, TPageParam>>
  | () => NonUndefinedGuard<InfiniteData<TQueryFnData, TPageParam>>
  | undefined;
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
