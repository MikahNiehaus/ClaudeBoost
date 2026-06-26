<!-- Source: github.com/dotnet/docs/docs/core\testing\mstest-analyzers\includes\test-class-rules.md | Tier: A | Topic: dotnet | Fetched: 2026-06-26 -->

The type declaring these methods should also respect the following rules:

- The type should be a `class`.
- The `class` should be `public` or `internal` (if the test project is using the `[DiscoverInternals]` attribute).
- The `class` shouldn't be `static`.
- If the `class` is `sealed`, it should be marked with `[TestClass]` (or a derived attribute).
