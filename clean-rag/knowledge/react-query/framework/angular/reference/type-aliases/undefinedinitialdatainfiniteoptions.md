<!-- Source: github.com/TanStack/query/docs/framework\angular\reference\type-aliases\UndefinedInitialDataInfiniteOptions.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: UndefinedInitialDataInfiniteOptions
title: UndefinedInitialDataInfiniteOptions
---

# Type Alias: UndefinedInitialDataInfiniteOptions\<TQueryFnData, TError, TData, TQueryKey, TPageParam\>

```ts
type UndefinedInitialDataInfiniteOptions<TQueryFnData, TError, TData, TQueryKey, TPageParam> = CreateInfiniteQueryOptions<TQueryFnData, TError, TData, TQueryKey, TPageParam> & object;
```

Defined in: [infinite-query-options.ts:13](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/infinite-query-options.ts#L13)

## Type Declaration

### initialData?

```ts
optional initialData: 
  | NonUndefinedGuard<InfiniteData<TQueryFnData, TPageParam>>
| InitialDataFunction<NonUndefinedGuard<InfiniteData<TQueryFnData, TPageParam>>>;
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
