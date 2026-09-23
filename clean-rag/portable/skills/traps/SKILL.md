---
name: traps
description: Lookup table of concrete reasoning failure modes that ship as bugs — dates and time zones, epoch units, mutation vs copy, async, floats and money, sort, division and modulo, regex and strings, familiar-API traps, closures in loops, boolean logic. Each row names the broken pattern and the fix. Read it BEFORE writing code that touches any of those categories, and read it as a test input generator when hunting for a bug. Trigger on: date arithmetic, timestamps, epochs, sorting, modulo on possibly negative values, regex, money or price arithmetic, async callbacks, closures in a loop, a condition mixing negation with && or ||, parseInt, JSON round-trips, list copying.
---

# Traps

Each row below names a concrete broken pattern and the fix. Find the sections
that apply to what the code actually does and follow their rows.

Two ways to use this:

- **Before writing.** You are about to touch one of these categories. Read that
  section's rows and write the code the row points at.
- **When hunting a bug.** Every row is a test input that breaks wrong code. Walk
  the matching sections against the diff and write the test each matching row
  implies. Nothing loads this automatically, so read it yourself when a diff touches one of these categories.

No row covers your case and the behavior is load-bearing? Run a one-line REPL
probe (`node -e` / `python -c`) and paste the output. Never guess.

## Dates & times
- Never add 86400s/24h for "next day" where local time matters -> use addDays / timedelta(days=1) / tz-aware arithmetic (DST breaks fixed offsets).
- Month arithmetic overflows on day 31: state in a comment what Jan 31 + 1 month must produce, then pick the API.
- JS: months are 0-indexed (`new Date(2024, 0, 15)` = Jan 15); getDay() = weekday, getDate() = day-of-month.
- JS parsing: `new Date('2024-01-15')` = UTC midnight; `new Date(2024, 0, 15)` = LOCAL midnight — mixing shifts dates a day.
- Year format token depends on the library family: Java/date-fns/Luxon (LDML tokens): yyyy, never YYYY (uppercase = week-numbering year, wrong near New Year). Moment/Day.js: YYYY IS the calendar year (their week-year is gggg/GGGG; lowercase yyyy prints LITERALLY in Day.js). Python strftime: %Y (%G is ISO week-year). Unsure which family? Probe 2024-12-30 with both tokens and paste the output.
- Python: never compare naive and aware datetimes; `datetime.utcnow()` is naive -> use `datetime.now(timezone.utc)`.
- Date-range filters on timestamps: `ts >= day AND ts < nextDay`, never `<= endOfDay`; annotate every range's inclusivity as `[a, b)`.
- Computed loop/slice/range bounds (pagination, chunking, windows): write a one-line trace for len=0,1,3 as a comment before the code, e.g. `// len=10,size=3 -> [0:3][3:6][6:9][9:10] = 4 chunks`; code disagrees with trace -> fix the code.
- After writing date arithmetic, trace three dates in a comment: Jan 31, Dec 31, a DST transition (e.g. 2024-03-10 US).

## Epochs & units
- Digit count: 10 = seconds, 13 = ms, 16 = μs, 19 = ns. JS Date.now()/getTime() = ms; new Date(n) expects ms; Python time.time() = s; JWT exp/iat = s; System.currentTimeMillis() = ms; Go Unix() = s.
- Name the unit into the variable: expiresAtSec, timeoutMs, maxBytes, amountCents. Every *1000 or /1000 gets a comment naming both units.

## Mutation vs copy
- JS mutating: sort, reverse, splice, push/pop/shift/unshift, fill. Copying: toSorted, toReversed, toSpliced (ES2023 — Node 20+; older targets: `[...x].sort()`), slice, concat, spread.
- Python: list.sort()/.reverse() mutate AND return None. sorted() returns a NEW list; reversed() returns a lazy ONE-SHOT iterator over the ORIGINAL (later mutations show through; second iteration is empty) -> `list(reversed(x))` or `x[::-1]` for a real copy.
- Python: `x = y` never copies; .copy()/list(y)/y[:] are SHALLOW -> copy.deepcopy for nested structures.
- `def f(x, acc=[])` persists across calls -> `acc=None` sentinel. `[[0]*n]*m` aliases every row -> comprehension. JSON round-trip drops Dates/undefined -> structuredClone (Node 17+).
- Before mutating anything that arrived as a parameter or came from shared state: write one line naming who else holds a reference; if anyone might, copy first.

## Async
- Every async call is awaited, `return await`-ed inside try/catch, .then-chained, or explicitly `void`-ed with `// fire-and-forget`. After editing async code: Grep the file for each async function name; for every hit not preceded by await/return/void on that line, justify it in one line.
- Never pass an async callback to forEach/filter/reduce -> `for..of` + await (sequential) or `await Promise.all(items.map(...))` (parallel); state which one and why.
- Never branch on an un-awaited call: `if (asyncFn())` is always truthy.
- A value read BEFORE an await and written AFTER it may be stale — re-read after the await or comment why no concurrent writer exists.

## Floats & money
- Never ==/=== computed floats -> tolerance (`Math.abs(a-b) < 1e-9`, math.isclose, pytest.approx) or integers.
- Money is ALWAYS integer minor units or Decimal; before finishing, grep the diff for arithmetic on price/amount/total/fee/balance and confirm no binary floats. `toFixed()` returns a STRING.

## Sort
- JS .sort() without a comparator is lexicographic: `[10,9,1].sort()` -> `[1,10,9]`. Always pass a comparator (or comment `// lexicographic intended`).
- Comparators return NUMBERS, never booleans: rewrite bare `>` as `a - b` (finite numbers), `localeCompare` (user-facing strings), or -1/0/1. `.sort()` MUTATES -> toSorted for a copy.

## Division & modulo
- Python // and % FLOOR (-1 % 5 = 4); JS/Java/C/Go/Rust % TRUNCATES (-1 % 5 = -1). Dividend can be negative? Trace one concrete negative value in a comment; nonnegative modulo = `((x % n) + n) % n`.
- JS numbers corrupt integers above 2^53: 64-bit IDs travel as STRINGS through JSON and JS.

## Regex & strings
- After writing any non-literal regex: probe it with `node -e`/`python -c` against one intended match, one near-miss, and the empty string — paste the outputs. Real inputs from the repo, not invented ones.
- Escape literal dots; anchor validations `^...$` (Python re.match anchors start only -> re.fullmatch); JS `str.replace(string, x)` replaces FIRST only -> replaceAll or /g; a reused /g regex keeps lastIndex state; `$` in replacements is special -> `$$`.
- Python `str.split()` (no arg) collapses whitespace runs — not `split(' ')`. JS `'👍'.length === 2` — use `[...str]` for user-visible truncation (code points; ZWJ emoji/combining marks still split — Intl.Segmenter for true graphemes).

## Familiar-API traps
- `['1','7','11'].map(parseInt)` -> `[1, NaN, 3]` (index becomes radix) -> use `Number` or `x => parseInt(x, 10)`.
- `typeof null === 'object'`; `NaN !== NaN` -> Number.isNaN. JSON.stringify drops undefined/functions; NaN/Infinity become null; Dates do not round-trip.
- Python `is` only for None/True/False (int/str interning passes in tests, fails in prod). `Array(3).map(f)` does nothing (holes) -> `Array.from({length: 3}, f)`.

## Closures in loops
- Deferred execution captures VARIABLES, not values: JS -> `let` in the for-header, never `var`; Python -> `lambda i=i: ...` or functools.partial; Go <1.22 -> `i := i`. State in one line which value each closure sees at CALL time.

## Boolean logic
- Negation mixed with &&/|| (or `not` with and/or), or 3+ clauses: write the truth-table rows where the expression is TRUE (up to 4 rows; more than 4 TRUE rows -> decompose into named booleans first); parenthesize every group; prefer naming the positive concept (`const isVisible = !hidden && !archived`).
- Branching on a negatively named flag (noCache, disabled, exclude*, skip*): comment what the TRUE branch does in positive words, or introduce a positively named local first.
- Mixed operator categories in one expression (bitwise+comparison, arithmetic in string concat, ?? with ||): parenthesize every subexpression — `(flags & MASK) == 0`.

## Truthiness
- Never truthiness-check a value that can be `0`, `""`, or `false` — compare to null/undefined/None explicitly. JS defaults use `??`, never `||`. Zero is data.

---

Source: the `TRAPS.md` table from the Guardrails Kit v1.0
(github.com/TheColliny/FableClaudeMDForOpus), taken verbatim. Do not paraphrase
a row when editing this file: each one names a specific broken pattern, and
softening the wording removes the thing that makes it checkable.
