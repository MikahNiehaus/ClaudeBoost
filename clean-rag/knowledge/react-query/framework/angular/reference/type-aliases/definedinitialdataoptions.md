<!-- Source: github.com/TanStack/query/docs/framework\angular\reference\type-aliases\DefinedInitialDataOptions.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: DefinedInitialDataOptions
title: DefinedInitialDataOptions
---

# Type Alias: DefinedInitialDataOptions\<TQueryFnData, TError, TData, TQueryKey\>

```ts
type DefinedInitialDataOptions<TQueryFnData, TError, TData, TQueryKey> = Omit<CreateQueryOptions<TQueryFnData, TError, TData, TQueryKey>, "queryFn"> & object;
```

Defined in: [query-options.ts:40](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/query-options.ts#L40)

## Type Declaration

### initialData

```ts
initialData: 
  | NonUndefinedGuard<TQueryFnData>
| () => NonUndefinedGuard<TQueryFnData>;
```

### queryFn?

```ts
optional queryFn: QueryFunction<TQueryFnData, TQueryKey>;
```

## Type Parameters

### TQueryFnData

`TQueryFnData` = `unknown`

### TError

`TError` = `DefaultError`

### TData

`TData` = `TQueryFnData`

### TQueryKey

`TQueryKey` *extends* `QueryKey` = `QueryKey`
