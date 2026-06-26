<!-- Source: github.com/TanStack/query/docs/framework\angular\reference\functions\provideIsRestoring.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: provideIsRestoring
title: provideIsRestoring
---

# Function: provideIsRestoring()

```ts
function provideIsRestoring(isRestoring): Provider;
```

Defined in: [inject-is-restoring.ts:43](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/inject-is-restoring.ts#L43)

Used by TanStack Query Angular persist client plugin to provide the signal that tracks the restore state

## Parameters

### isRestoring

`Signal`\<`boolean`\>

a readonly signal that returns a boolean

## Returns

`Provider`

Provider for the `isRestoring` signal
