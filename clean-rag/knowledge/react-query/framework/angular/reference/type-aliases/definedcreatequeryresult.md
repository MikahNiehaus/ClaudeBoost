<!-- Source: github.com/TanStack/query/docs/framework\angular\reference\type-aliases\DefinedCreateQueryResult.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: DefinedCreateQueryResult
title: DefinedCreateQueryResult
---

# Type Alias: DefinedCreateQueryResult\<TData, TError, TState\>

```ts
type DefinedCreateQueryResult<TData, TError, TState> = BaseQueryNarrowing<TData, TError> & MapToSignals<OmitKeyof<TState, keyof BaseQueryNarrowing, "safely">>;
```

Defined in: [types.ts:110](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/types.ts#L110)

## Type Parameters

### TData

`TData` = `unknown`

### TError

`TError` = `DefaultError`

### TState

`TState` = `DefinedQueryObserverResult`\<`TData`, `TError`\>
