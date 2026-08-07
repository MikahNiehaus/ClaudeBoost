"""C# invocation_expression call edges, and their downstream resolution.

extract_edges used to emit no "calls" edge for a .cs file at all: the calls
block was gated on import_aliases, which is only ever populated for
python/js/ts, so a C# file always hit that gate falsy and short circuited
before language was even checked (edge_extraction.py, the block starting
"if import_aliases and language in"). A C# project therefore had no call
neighbours in its graph.

These tests cover the csharp invocation_expression branch and the C#
fallback in SQLiteGraphStore.resolve_target_files. The behaviour they pin:

1. invocation_expression produces "calls" edges for a bare call and for a
   member access on a plain identifier.
2. A qualifier that is not a plain identifier (this, a chained call, a
   generic instantiation) is skipped, since it cannot resolve to a file.
3. A qualifier that C# naming convention says cannot be a type (camelCase,
   _camelCase, s_camelCase: a local, a parameter or a private field) is
   skipped too, for the same reason. It can never name a file.
4. The imports, inherits and implements edge types are unchanged.
5. An unresolvable using directive naming a namespace outside the project is
   marked "_external_", not left empty.
6. A symbol whose first segment IS a project namespace is left empty,
   available for future resolution, not marked external.
7. "_external_" means a third party or stdlib dependency and nothing else.
   It is what /status reports as a project's dependency health, so an
   unresolvable local identifier must never be stamped with it.
"""

import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLEAN_RAG))

from server.edge_extraction import extract_edges, get_language  # noqa: E402
from server.graph_store import (  # noqa: E402
    GraphEdge,
    SQLiteGraphStore,
    _is_external_symbol,
    _resolve_symbol,
)
from server.indexing import _register_file_variants  # noqa: E402

pytest.importorskip("tree_sitter_language_pack")


def _calls(src: str, filename: str = "Bar.cs") -> list[GraphEdge]:
    edges = extract_edges(src, "csharp", filename)
    return [e for e in edges if e.edge_type == "calls"]


class TestInvocationExpressionEmitsCalls:
    def test_bare_identifier_call_emits_its_own_name(self):
        edges = _calls("class C { void M() { Validate(); } }")
        assert [e.target_symbol for e in edges] == ["Validate"]
        assert edges[0].confidence == "INFERRED"
        assert edges[0].source_symbol == "<call>"

    def test_member_access_on_a_plain_identifier_emits_the_qualifier(self):
        """OrderService.Process(1) must resolve toward OrderService, the
        type, not Process, the method: a bare method name has no file to
        land on, the qualifier does (one public type per file)."""
        edges = _calls("class C { void M() { OrderService.Process(1); } }")
        assert [e.target_symbol for e in edges] == ["OrderService"]

    def test_a_private_field_qualifier_is_not_a_type_and_is_skipped(self):
        """_logger is a private field, and a field never names a file, so it
        is not a candidate neighbour. The .NET runtime coding style makes the
        two cases tellable apart without any semantic analysis: PascalCase for
        type names and namespaces, camelCase for locals, parameters and
        private fields, with a leading underscore on instance fields
        (dotnet/docs, csharp/fundamentals/coding-style/identifier-names.md).

        Measured on 300 real .cs files, dropping these removed 845 of 1536
        distinct call targets while losing none of the targets that actually
        resolved to a project file."""
        edges = _calls('class C { void M() { _logger.LogInformation("x"); } }')
        assert edges == [], f"a private field is not a file neighbour, got {edges}"

    @pytest.mark.parametrize("qualifier", ["_logger", "s_cache", "builder", "b", "i"])
    def test_no_camel_case_or_underscored_qualifier_survives(self, qualifier):
        edges = _calls("class C { void M() { %s.Do(); } }" % qualifier)
        assert edges == [], f"{qualifier}.Do() must not emit an edge, got {edges}"

    @pytest.mark.parametrize("qualifier", ["OrderService", "File", "HttpClient"])
    def test_every_pascal_case_qualifier_still_survives(self, qualifier):
        """The control for the filter above: it must not be swallowing the
        qualifiers that are the whole point of the calls edge."""
        edges = _calls("class C { void M() { %s.Do(); } }" % qualifier)
        assert [e.target_symbol for e in edges] == [qualifier]


class TestNonIdentifierQualifierIsSkipped:
    def test_this_expression_qualifier_never_emits_this(self):
        edges = _calls("class C { void M() { this.Helper(); } }")
        assert edges == [], f"this.Helper() must not emit an edge, got {edges}"

    def test_chained_member_access_a_b_c_method_does_not_crash_or_leak_a_or_b(self):
        edges = _calls("class C { void M() { a.b.c.Method(); } }")
        assert edges == [], f"a.b.c.Method() has no bare-identifier qualifier, got {edges}"

    def test_result_of_a_call_used_as_a_qualifier_does_not_emit_the_outer_call(self):
        """GetThing().Do(): the OUTER call's qualifier is an invocation_expression,
        not an identifier, so it must be skipped. The INNER call, GetThing(),
        is itself visited by the walk and legitimately emits 'GetThing'."""
        edges = _calls("class C { void M() { GetThing().Do(); } }")
        assert [e.target_symbol for e in edges] == ["GetThing"], (
            "expected only the inner bare call to survive, got "
            f"{[e.target_symbol for e in edges]}"
        )

    def test_generic_static_call_qualifier_is_not_a_plain_identifier(self):
        edges = _calls("class C { void M() { Foo<T>.Bar(); } }")
        assert edges == [], f"Foo<T>.Bar() qualifier is a generic_name, got {edges}"

    def test_object_creation_then_call_does_not_emit_the_constructed_type(self):
        edges = _calls("class C { void M() { new Thing().Go(); } }")
        assert edges == [], f"new Thing().Go() qualifier is a creation expression, got {edges}"

    def test_deeply_nested_and_generic_calls_never_raise(self):
        """No input shape here should crash extract_edges. A crash would be
        silently swallowed by indexing.py's try/except around extract_edges,
        which would look like zero edges rather than a real failure."""
        src = """
        class C {
            void M() {
                a.b.c.d.e.Method();
                Foo<Bar<Baz>>.Qux<int>();
                ((IFoo)obj).DoThing();
                obj?.MaybeCall();
                (a ? b : c).Call();
            }
        }
        """
        edges = _calls(src)  # must not raise
        assert isinstance(edges, list)


class TestPreExistingCSharpEdgeTypesUnchanged:
    def test_using_directive_still_emits_imports(self):
        edges = extract_edges("using System.Collections.Generic;", "csharp", "F.cs")
        imports = [e for e in edges if e.edge_type == "imports"]
        assert [e.target_symbol for e in imports] == ["System.Collections.Generic"]

    def test_interface_prefixed_base_still_emits_implements(self):
        src = "class Foo : IDisposable { }"
        edges = extract_edges(src, "csharp", "F.cs")
        rel = [(e.edge_type, e.target_symbol) for e in edges if e.edge_type in ("inherits", "implements")]
        assert rel == [("implements", "IDisposable")]

    def test_non_interface_base_still_emits_inherits(self):
        src = "class Foo : BaseThing { }"
        edges = extract_edges(src, "csharp", "F.cs")
        rel = [(e.edge_type, e.target_symbol) for e in edges if e.edge_type in ("inherits", "implements")]
        assert rel == [("inherits", "BaseThing")]

    def test_no_other_language_gained_a_calls_edge(self):
        """Only the csharp branch emits an unaliased call edge. Python's call
        detection stays gated on import_aliases and must stay silent for a
        bare, alias-less call."""
        py_src = "def f():\n    validate()\n"
        edges = extract_edges(py_src, "python", "f.py")
        assert [e for e in edges if e.edge_type == "calls"] == []


class TestUsingAliasNeverProducesASpace:
    """The python fallback in resolve_target_files strips ' as ' before
    splitting; the C# fallback does not. Confirms that gap is not
    reachable through real C# using-alias syntax: using_directive's own
    extraction (unchanged by this diff) walks depth-first and returns the
    alias's own identifier, never the aliased qualified_name, so a C# using
    alias directive can never hand target_symbol a string containing ' as '
    in the first place."""

    def test_using_alias_directive_yields_the_alias_name_not_the_target_with_as(self):
        edges = extract_edges(
            "using Alias = Some.Namespace.Thing;", "csharp", "F.cs",
        )
        imports = [e.target_symbol for e in edges if e.edge_type == "imports"]
        assert imports == ["Alias"]
        assert not any(" as " in s for s in imports)


class TestCSharpFallbackResolution:
    """Direct tests of the C# branch of resolve_target_files, bypassing
    extraction entirely so the resolution contract is pinned regardless of
    what upstream heuristic produced the row.

    These rows are "imports" because that is the only C# edge type whose
    target is a namespace. A using directive names a namespace, so asking
    whether its first segment belongs to the project is a real question.
    The other C# edge types carry a bare type or method name (a call
    qualifier, a base type), where the same question has no meaning."""

    def _store(self, tmp_path):
        return SQLiteGraphStore(str(tmp_path / "graph.db"))

    def test_unresolvable_namespace_outside_the_project_becomes_external(self, tmp_path):
        store = self._store(tmp_path)
        store.add_edges([GraphEdge(
            source_file="Services/OrderService.cs", source_symbol="<module>",
            target_file="", target_symbol="Stripe.Checkout.Session",
            edge_type="imports", confidence="EXTRACTED",
        )])
        file_map = {}
        _register_file_variants("Services/OrderService.cs", file_map)

        resolved_count = store.resolve_target_files(file_map)
        assert resolved_count == 0
        rows = [e for e in store.get_all_edges() if e.target_symbol == "Stripe.Checkout.Session"]
        assert rows[0].target_file == "_external_", (
            "an unresolvable using directive whose first segment ('Stripe') is "
            f"not a project namespace must be marked external, got {rows[0].target_file!r}"
        )

    def test_symbol_matching_a_project_namespace_is_left_empty_not_external(self, tmp_path):
        """Stays available for future resolution, is not mislabeled as a
        third party dependency."""
        store = self._store(tmp_path)
        store.add_edges([GraphEdge(
            source_file="Services/OrderService.cs", source_symbol="<module>",
            target_file="", target_symbol="Billing.NonExistentHelper",
            edge_type="imports", confidence="EXTRACTED",
        )])
        file_map = {}
        # "Billing" becomes a real project namespace segment via this file,
        # even though NonExistentHelper itself is not a real file.
        _register_file_variants("Billing/InvoiceBuilder.cs", file_map)
        _register_file_variants("Services/OrderService.cs", file_map)

        store.resolve_target_files(file_map)
        rows = [e for e in store.get_all_edges() if e.target_symbol == "Billing.NonExistentHelper"]
        assert rows[0].target_file == "", (
            f"'Billing' is a real project namespace, must stay empty, "
            f"got {rows[0].target_file!r}"
        )

    def test_a_dotted_project_folder_is_recognised_as_its_own_namespace(self, tmp_path):
        """A .NET folder carries the dotted namespace it holds, so
        "ViveryAscend.API/" is namespace ViveryAscend.API and "ViveryAscend"
        is a project namespace too. Splitting only on "/" leaves the first
        segment of "using ViveryAscend.API.Services;" matching no folder, and
        the project's own code gets filed under _external_. Measured on 300
        real .cs files, that was 507 of the 514 symbols the fallback marked
        external."""
        store = self._store(tmp_path)
        store.add_edges([GraphEdge(
            source_file="ViveryAscend.API/Controllers/OrderController.cs",
            source_symbol="<module>", target_file="",
            target_symbol="ViveryAscend.API.Services",
            edge_type="imports", confidence="EXTRACTED",
        )])
        file_map = {}
        _register_file_variants(
            "ViveryAscend.API/Controllers/OrderController.cs", file_map,
        )

        store.resolve_target_files(file_map)
        rows = [e for e in store.get_all_edges()
                if e.target_symbol == "ViveryAscend.API.Services"]
        assert rows[0].target_file == "", (
            "the project's own namespace must never be called a third party "
            f"dependency, got {rows[0].target_file!r}"
        )

    def test_cshtml_source_file_gets_the_same_fallback_as_cs(self, tmp_path):
        store = self._store(tmp_path)
        store.add_edges([GraphEdge(
            source_file="Views/Order/Index.cshtml", source_symbol="<call>",
            target_file="", target_symbol="Stripe.Checkout.Session",
            edge_type="imports", confidence="EXTRACTED",
        )])
        file_map = {}
        _register_file_variants("Views/Order/Index.cshtml", file_map)

        store.resolve_target_files(file_map)
        rows = [e for e in store.get_all_edges() if e.target_symbol == "Stripe.Checkout.Session"]
        assert rows[0].target_file == "_external_"


class TestCshtmlNeverActuallyReachesExtraction:
    """Razor is indexed as chunks but no edge is extracted from it. The
    extraction branch is keyed on language == 'csharp', and
    get_language('.cshtml') returns None (no _EXT_OVERRIDES entry, and
    grep-ast does not classify it either), while indexing.py only calls
    extract_edges when `if lang:` is true. So the real pipeline can never
    produce an edge whose source_file ends in .cshtml.

    resolve_target_files still names the suffix, because _is_external_symbol
    already carries the same ('.cs', '.cshtml') tuple and the two have to
    agree about what a C# source file is. Dropping the suffix from one of
    them would leave razor half supported instead of not supported. These
    tests exist so that whoever adds razor edge extraction finds the gap
    stated rather than having to rediscover it."""

    def test_get_language_returns_none_for_cshtml(self):
        assert get_language("Views/Order/Index.cshtml") is None

    def test_get_language_returns_csharp_for_cs(self):
        assert get_language("Services/OrderService.cs") == "csharp"


class TestProjectNamespaceCollisionDefeatsExternalDetection:
    """project_namespaces is built from every path segment of every
    file_map key (resolve_target_files, "Build set of project namespace
    segments"). A project with a folder that happens to share a name with a
    real, unlisted third party namespace poisons that set: a genuinely
    external symbol whose first segment matches the folder name is judged
    to be a project namespace and left empty forever, instead of being
    marked external. This is not hypothetical: the real target project
    (Nectar) has ViveryAscend.Function/Helpers/Twilio/ containing .cs files,
    though that specific case is caught upstream by the hardcoded
    _CS_EXTERNAL_PREFIXES list before the new fallback ever runs. This test
    picks a namespace that is NOT on that hardcoded list, to isolate the
    fallback's own behavior.

    Known and accepted, not fixed here: it mirrors the Python fallback
    directly above it, it predates the C# branch, and it fails safe. The
    symbol stays empty, which understates the dependency count rather than
    inventing one, and an empty target is inert in traversal either way."""

    def test_folder_name_collision_with_an_unlisted_third_party_namespace(self, tmp_path):
        assert "Stripe" not in __import__(
            "server.graph_store", fromlist=["_CS_EXTERNAL_PREFIXES"],
        )._CS_EXTERNAL_PREFIXES, "pick a namespace absent from the hardcoded list"

        store = SQLiteGraphStore(str(tmp_path / "graph.db"))
        store.add_edges([GraphEdge(
            source_file="Services/PaymentService.cs", source_symbol="<module>",
            target_file="", target_symbol="Stripe.Checkout.Session",
            edge_type="imports", confidence="EXTRACTED",
        )])
        file_map = {}
        # A project folder that happens to be named "Stripe", unrelated to
        # the Stripe SDK, e.g. a local extension-methods folder.
        _register_file_variants("Extensions/Stripe/CardHelpers.cs", file_map)
        _register_file_variants("Services/PaymentService.cs", file_map)

        store.resolve_target_files(file_map)
        rows = [e for e in store.get_all_edges() if e.target_symbol == "Stripe.Checkout.Session"]
        assert rows[0].target_file == "", (
            "demonstrates the collision: a genuinely external symbol "
            "(Stripe.Checkout.Session, not resolvable, not on the hardcoded "
            "external list) is judged 'ours' because a project folder "
            "happens to be named Stripe, and stays empty instead of "
            f"external, got {rows[0].target_file!r}"
        )


class TestExternalLabelMeansThirdPartyOnly:
    """/status reports the _external_ count as a project's dependency health,
    so the label has to keep meaning "third party or stdlib". Two things
    used to break that on a C# project and both are covered here.

    Measured on a 300 file sample of a real C# codebase: the label was
    carried by 953 distinct symbols across four edge types, 49 of them the
    project's own namespaces and the rest including loop counters and mock
    fields. It is now carried by 96 symbols on imports edges alone, every
    one of them a real BCL or NuGet namespace, with no loss in the number of
    call targets that resolve to a real project file."""

    def test_an_unresolvable_local_identifier_is_never_called_a_dependency(self, tmp_path):
        """A lambda parameter named 'b' and a real third party namespace must
        not end up with the same stamp. 'b' is unresolvable and matches no
        project folder, which is exactly the shape that used to be swept into
        _external_."""
        store = SQLiteGraphStore(str(tmp_path / "graph.db"))
        store.add_edges([
            GraphEdge(
                source_file="Migrations/20260101_Init.cs", source_symbol="<call>",
                target_file="", target_symbol="b",
                edge_type="calls", confidence="INFERRED",
            ),
            GraphEdge(
                source_file="Services/PaymentService.cs", source_symbol="<module>",
                target_file="", target_symbol="Stripe.Checkout.Session",
                edge_type="imports", confidence="EXTRACTED",
            ),
        ])
        file_map = {}
        _register_file_variants("Migrations/20260101_Init.cs", file_map)
        _register_file_variants("Services/PaymentService.cs", file_map)

        resolved_count = store.resolve_target_files(file_map)
        rows = {e.target_symbol: e.target_file for e in store.get_all_edges()}

        assert resolved_count == 0
        assert rows["Stripe.Checkout.Session"] == "_external_", (
            "a real third party namespace must still be marked external, got "
            f"{rows['Stripe.Checkout.Session']!r}"
        )
        assert rows["b"] == "", (
            "an unresolvable local identifier must stay empty, otherwise it is "
            f"indistinguishable from a real dependency, got {rows['b']!r}"
        )

    def test_a_lambda_parameter_never_becomes_an_edge_in_the_first_place(self):
        """The cheaper half of the same guarantee: a generated migration body
        is the worst real case (one such file emitted 4243 raw edges, all
        targeting the lambda parameter 'b'), and none of it is written now."""
        src = """
        class M {
            void Up(MigrationBuilder migrationBuilder) {
                migrationBuilder.CreateTable(
                    name: "Icons",
                    columns: table => new { Id = table.Column<int>() });
                modelBuilder.Entity("IconSet", b => { b.Property<int>("Id"); });
            }
        }
        """
        assert _calls(src) == [], (
            f"generated migration bodies must emit no call edges, got "
            f"{[e.target_symbol for e in _calls(src)]}"
        )

    def test_inherits_and_implements_are_not_swept_into_external_either(self, tmp_path):
        """A base type is a type name, not a namespace, so the namespace
        comparison cannot classify it. IDisposable really is external, but
        nothing here knows that, and guessing is what corrupts the label."""
        store = SQLiteGraphStore(str(tmp_path / "graph.db"))
        store.add_edges([GraphEdge(
            source_file="Services/OrderService.cs", source_symbol="OrderService",
            target_file="", target_symbol="IDisposable",
            edge_type="implements", confidence="EXTRACTED",
        )])
        file_map = {}
        _register_file_variants("Services/OrderService.cs", file_map)

        store.resolve_target_files(file_map)
        rows = [e for e in store.get_all_edges() if e.target_symbol == "IDisposable"]
        assert rows[0].target_file == "", (
            f"a base type must stay empty, not be guessed external, got "
            f"{rows[0].target_file!r}"
        )


class TestEmptyAndExternalTargetsAreInertInTraversal:
    """Why an unresolved row is harmless to search.
    get_neighbours(depth=1) returns the raw
    edge row incident on the seed regardless of whether target_file
    resolved, so a caller inspecting a depth-1 result still sees the empty
    or '_external_' row (this is by design: depth=1 is "what edges touch
    this file", not "what files does this reach"). The inertness is at the
    NEXT hop: `_next_hop_neighbor` (graph_store.py, "matched because tf was
    in the frontier") refuses to promote '' or '_external_' into the
    frontier, so a depth-2 traversal can never walk further from a node
    that never resolved to begin with. That is where an empty or external
    C# calls edge, real or noise, stops mattering."""

    def test_depth_one_still_reports_the_raw_edge_even_when_unresolved(self, tmp_path):
        """Control: confirms get_neighbours is not itself filtering, so the
        depth=2 test below is exercising the frontier-expansion guard and
        not a no-op query."""
        store = SQLiteGraphStore(str(tmp_path / "graph.db"))
        store.add_edges([GraphEdge(
            source_file="Services/OrderService.cs", source_symbol="<call>",
            target_file="", target_symbol="Billing.NonExistentHelper",
            edge_type="calls", confidence="INFERRED",
        )])
        neighbors = store.get_neighbours("Services/OrderService.cs", depth=1)
        assert len(neighbors) == 1

    def test_an_unresolved_calls_edge_never_extends_a_depth_two_traversal(self, tmp_path):
        """A must not reach C through B when A->B is an unresolved (empty
        target_file) calls edge, even though a real B->C edge exists,
        because '' can never be promoted into the frontier."""
        store = SQLiteGraphStore(str(tmp_path / "graph.db"))
        store.add_edges([
            GraphEdge(
                source_file="Services/OrderService.cs", source_symbol="<call>",
                target_file="", target_symbol="Billing.NonExistentHelper",
                edge_type="calls", confidence="INFERRED",
            ),
            # An edge FROM the same empty target_file value, unrelated to
            # OrderService, that must never leak into OrderService's
            # traversal just because both rows share target_file=''.
            GraphEdge(
                source_file="", source_symbol="<call>",
                target_file="Unrelated/Leaked.cs", target_symbol="Leaked",
                edge_type="calls", confidence="INFERRED",
            ),
        ])
        neighbors = store.get_neighbours("Services/OrderService.cs", depth=2)
        leaked = [e for e in neighbors if e.target_file == "Unrelated/Leaked.cs"]
        assert leaked == [], (
            f"an unrelated edge sharing the empty target_file sentinel leaked into "
            f"a depth-2 traversal from a different seed: {leaked}"
        )

    def test_an_external_calls_edge_never_extends_a_depth_two_traversal(self, tmp_path):
        store = SQLiteGraphStore(str(tmp_path / "graph.db"))
        store.add_edges([
            GraphEdge(
                source_file="Services/OrderService.cs", source_symbol="<call>",
                target_file="_external_", target_symbol="Stripe.Checkout.Session",
                edge_type="calls", confidence="INFERRED",
            ),
            GraphEdge(
                source_file="_external_", source_symbol="<call>",
                target_file="Unrelated/Leaked.cs", target_symbol="Leaked",
                edge_type="calls", confidence="INFERRED",
            ),
        ])
        neighbors = store.get_neighbours("Services/OrderService.cs", depth=2)
        leaked = [e for e in neighbors if e.target_file == "Unrelated/Leaked.cs"]
        assert leaked == [], (
            f"an unrelated edge sharing the _external_ sentinel leaked into "
            f"a depth-2 traversal from a different seed: {leaked}"
        )

    def test_a_genuinely_resolved_calls_edge_does_extend_a_depth_two_traversal(self, tmp_path):
        """Control: proves the guard above is real filtering, not
        get_neighbours silently failing to expand at all."""
        store = SQLiteGraphStore(str(tmp_path / "graph.db"))
        store.add_edges([
            GraphEdge(
                source_file="Services/OrderService.cs", source_symbol="<call>",
                target_file="Services/PaymentGateway.cs", target_symbol="PaymentGateway",
                edge_type="calls", confidence="INFERRED",
            ),
            GraphEdge(
                source_file="Services/PaymentGateway.cs", source_symbol="<call>",
                target_file="Services/Reachable.cs", target_symbol="Reachable",
                edge_type="calls", confidence="INFERRED",
            ),
        ])
        neighbors = store.get_neighbours("Services/OrderService.cs", depth=2)
        assert any(e.target_file == "Services/Reachable.cs" for e in neighbors), (
            "a real two-hop chain must be reachable at depth=2, otherwise the "
            "two negative tests above are not proving anything"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
