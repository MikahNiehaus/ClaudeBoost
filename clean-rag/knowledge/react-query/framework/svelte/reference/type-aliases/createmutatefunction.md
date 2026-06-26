<!-- Source: github.com/TanStack/query/docs/framework\svelte\reference\type-aliases\CreateMutateFunction.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: CreateMutateFunction
title: CreateMutateFunction
---

# Type Alias: CreateMutateFunction()\<TData, TError, TVariables, TOnMutateResult\>

```ts
type CreateMutateFunction<TData, TError, TVariables, TOnMutateResult> = (...args) => void;
```

Defined in: [packages/svelte-query/src/types.ts:96](https://github.com/TanStack/query/blob/main/packages/svelte-query/src/types.ts#L96)

## Type Parameters

### TData

`TData` = `unknown`

### TError

`TError` = `DefaultError`

### TVariables

`TVariables` = `void`

### TOnMutateResult

`TOnMutateResult` = `unknown`

## Parameters

### args

...`Parameters`\<`MutateFunction`\<`TData`, `TError`, `TVariables`, `TOnMutateResult`\>\>

## Returns

`void`
