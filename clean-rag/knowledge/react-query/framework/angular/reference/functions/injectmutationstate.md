<!-- Source: github.com/TanStack/query/docs/framework\angular\reference\functions\injectMutationState.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: injectMutationState
title: injectMutationState
---

# Function: injectMutationState()

```ts
function injectMutationState<TResult>(injectMutationStateFn, options?): Signal<TResult[]>;
```

Defined in: [inject-mutation-state.ts:60](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/inject-mutation-state.ts#L60)

Injects a signal that tracks the state of all mutations.

## Type Parameters

### TResult

`TResult` = `MutationState`\<`unknown`, `Error`, `unknown`, `unknown`\>

## Parameters

### injectMutationStateFn

() => `MutationStateOptions`\<`TResult`\>

A function that returns mutation state options.

### options?

[`InjectMutationStateOptions`](../interfaces/InjectMutationStateOptions.md)

The Angular injector to use.

## Returns

`Signal`\<`TResult`[]\>

The signal that tracks the state of all mutations.
