<!-- Source: github.com/TanStack/query/docs/framework\svelte\reference\type-aliases\DefinedInitialDataOptions.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: DefinedInitialDataOptions
title: DefinedInitialDataOptions
---

# Type Alias: DefinedInitialDataOptions\<TQueryFnData, TError, TData, TQueryKey\>

```ts
type DefinedInitialDataOptions<TQueryFnData, TError, TData, TQueryKey> = CreateQueryOptions<TQueryFnData, TError, TData, TQueryKey> & object;
```

Defined in: [packages/svelte-query/src/queryOptions.ts:19](https://github.com/TanStack/query/blob/main/packages/svelte-query/src/queryOptions.ts#L19)

## Type Declaration

### initialData

```ts
initialData: 
  | NonUndefinedGuard<TQueryFnData>
| () => NonUndefinedGuard<TQueryFnData>;
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
