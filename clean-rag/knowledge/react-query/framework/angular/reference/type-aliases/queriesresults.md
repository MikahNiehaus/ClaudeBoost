<!-- Source: github.com/TanStack/query/docs/framework\angular\reference\type-aliases\QueriesResults.md | Tier: A | Topic: react-query | Fetched: 2026-06-26 -->

---
id: QueriesResults
title: QueriesResults
---

# Type Alias: QueriesResults\<T, TResults, TDepth\>

```ts
type QueriesResults<T, TResults, TDepth> = TDepth["length"] extends MAXIMUM_DEPTH ? CreateQueryResult[] : T extends [] ? [] : T extends [infer Head] ? [...TResults, GetCreateQueryResult<Head>] : T extends [infer Head, ...(infer Tails)] ? QueriesResults<[...Tails], [...TResults, GetCreateQueryResult<Head>], [...TDepth, 1]> : { [K in keyof T]: GetCreateQueryResult<T[K]> };
```

Defined in: [inject-queries.ts:186](https://github.com/TanStack/query/blob/main/packages/angular-query-experimental/src/inject-queries.ts#L186)

QueriesResults reducer recursively maps type param to results

## Type Parameters

### T

`T` *extends* `any`[]

### TResults

`TResults` *extends* `any`[] = \[\]

### TDepth

`TDepth` *extends* `ReadonlyArray`\<`number`\> = \[\]
