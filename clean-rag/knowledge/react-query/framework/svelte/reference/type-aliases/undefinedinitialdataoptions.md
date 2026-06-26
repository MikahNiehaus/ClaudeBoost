<!-- Source: github.com/TanStack/query/docs/framework\svelte\reference\type-aliases\UndefinedInitialDataOptions.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: UndefinedInitialDataOptions
title: UndefinedInitialDataOptions
---

# Type Alias: UndefinedInitialDataOptions\<TQueryFnData, TError, TData, TQueryKey\>

```ts
type UndefinedInitialDataOptions<TQueryFnData, TError, TData, TQueryKey> = CreateQueryOptions<TQueryFnData, TError, TData, TQueryKey> & object;
```

Defined in: [packages/svelte-query/src/queryOptions.ts:10](https://github.com/TanStack/query/blob/main/packages/svelte-query/src/queryOptions.ts#L10)

## Type Declaration

### initialData?

```ts
optional initialData: InitialDataFunction<NonUndefinedGuard<TQueryFnData>>;
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
