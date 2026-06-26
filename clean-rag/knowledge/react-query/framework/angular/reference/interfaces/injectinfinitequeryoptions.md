<!-- Source: github.com/TanStack/query/docs/framework\angular\reference\interfaces\InjectInfiniteQueryOptions.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: InjectInfiniteQueryOptions
title: InjectInfiniteQueryOptions
---

# Interface: InjectInfiniteQueryOptions

Defined in: [inject-infinite-query.ts:25](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/inject-infinite-query.ts#L25)

## Properties

### injector?

```ts
optional injector: Injector;
```

Defined in: [inject-infinite-query.ts:31](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/inject-infinite-query.ts#L31)

The `Injector` in which to create the infinite query.

If this is not provided, the current injection context will be used instead (via `inject`).
