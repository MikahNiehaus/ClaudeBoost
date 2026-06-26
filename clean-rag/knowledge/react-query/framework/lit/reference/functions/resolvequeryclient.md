<!-- Source: github.com/TanStack/query/docs/framework\lit\reference\functions\resolveQueryClient.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: resolveQueryClient
title: resolveQueryClient
---

# Function: resolveQueryClient()

```ts
function resolveQueryClient(explicit?): QueryClient;
```

Defined in: [packages/lit-query/src/context.ts:118](https://github.com/TanStack/query/blob/main/packages/lit-query/src/context.ts#L118)

Resolves an explicit `QueryClient` or falls back to `useQueryClient`.

## Parameters

### explicit?

`QueryClient`

Optional client supplied by the caller.

## Returns

`QueryClient`

The explicit client when provided, otherwise the current default
client.
