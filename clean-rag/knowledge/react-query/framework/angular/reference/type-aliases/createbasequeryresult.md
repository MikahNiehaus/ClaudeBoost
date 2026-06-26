<!-- Source: github.com/TanStack/query/docs/framework\angular\reference\type-aliases\CreateBaseQueryResult.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: CreateBaseQueryResult
title: CreateBaseQueryResult
---

# Type Alias: CreateBaseQueryResult\<TData, TError, TState\>

```ts
type CreateBaseQueryResult<TData, TError, TState> = BaseQueryNarrowing<TData, TError> & MapToSignals<OmitKeyof<TState, keyof BaseQueryNarrowing, "safely">>;
```

Defined in: [types.ts:98](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/types.ts#L98)

## Type Parameters

### TData

`TData` = `unknown`

### TError

`TError` = `DefaultError`

### TState

`TState` = `QueryObserverResult`\<`TData`, `TError`\>
