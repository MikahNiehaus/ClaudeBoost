<!-- Source: https://pydevtools.com/handbook/how-to/how-to-configure-recommended-ruff-defaults/ | Tier: B | Topic: python-deprecation | Fetched: 2026-06-26 -->

Skip to content

[ Python Developer Tooling Handbook ](/)

Handbook

  * [Tutorial](/handbook/tutorial)
  * [How To](/handbook/how-to)
  * [Explanation](/handbook/explanation)
  * [Reference](/handbook/reference)



[Topics ](/handbook/topics/)[Blog ](/blog)[About ](/about)[Privacy ](/privacy) [ Github ](https://github.com/python-developer-tooling-handbook "Github")

  * Light 
  * Dark 
  * System 



  * [Handbook](/handbook)
  * [Topics](/handbook/topics/)
  * [Blog](/blog)
  * [About](/about)
  * [Privacy](/privacy)
  * [Github](https://github.com/python-developer-tooling-handbook)
  * [Theme]()

[← Handbook](/handbook/)

  * [Tutorial](/handbook/tutorial/)
  * [How To](/handbook/how-to/)
  * [Explanation](/handbook/explanation/)
  * [Reference](/handbook/reference/)



How To

### Linting, Formatting & Type Checking

  * [add type annotations to a Python project with pyrefly infer](/handbook/how-to/how-to-add-type-annotations-with-pyrefly-infer/)
  * [configure mypy and django-stubs in a uv project](/handbook/how-to/how-to-configure-mypy-and-django-stubs-in-a-uv-project/)
  * [configure mypy strict mode](/handbook/how-to/how-to-configure-mypy-strict-mode/)
  * [configure recommended Ruff defaults](/handbook/how-to/how-to-configure-recommended-ruff-defaults/)
  * [configure Ruff for Django](/handbook/how-to/how-to-configure-ruff-for-django/)
  * [Disable Ruff Rules for a Block of Code](/handbook/how-to/how-to-disable-ruff-rules-for-a-block-of-code/)
  * [Disable the Ruff Formatter for a Block of Code](/handbook/how-to/how-to-disable-the-ruff-formatter-for-a-block-of-code/)
  * [Enable Ruff Security Rules](/handbook/how-to/how-to-enable-ruff-security-rules/)
  * [format pyproject.toml with taplo](/handbook/how-to/how-to-format-pyproject-toml-with-taplo/)
  * [gradually adopt type checking in an existing Python project](/handbook/how-to/how-to-gradually-adopt-type-checking-in-an-existing-python-project/)
  * [sort Python imports with Ruff](/handbook/how-to/how-to-sort-python-imports-with-ruff/)
  * [test a Python library against multiple type checkers](/handbook/how-to/how-to-test-a-python-library-against-multiple-type-checkers/)
  * [try the ty type checker](/handbook/how-to/how-to-try-the-ty-type-checker/)

[← All How To groups](/handbook/how-to/#code-quality)

[ Sponsor this project ](https://github.com/sponsors/python-developer-tooling-handbook)

On this page

  * Adding the Configuration 
  * Running the Linter 
  * Understanding the Rule Categories 
  * Pyflakes (F) 
  * PyCodeStyle Errors (E) and Warnings (W) 
  * Import Sorting (I) 
  * Python Upgrades (UP) 
  * Comprehensions (C4) 
  * Future Annotations (FA) 
  * String Concatenation (ISC) 
  * Import Conventions (ICN) 
  * Return Practices (RET) 
  * Simplifications (SIM) 
  * Tidy Imports (TID) 
  * Type Checking Imports (TC) 
  * Pathlib Usage (PTH) 
  * TODO Discipline (TD) 
  * NumPy Conventions (NPY) 
  * Refurb (FURB) 
  * Selective Rule Disabling 



Scroll to top

Tim Hopper

Research engineer and creator of the Python Developer Tooling Handbook.

[LinkedIn](https://linkedin.com/in/tdhopper) [Resume](https://resume.tdhopper.com) [GitHub](https://github.com/tdhopper) [X](https://x.com/tdhopper)

# How to configure recommended Ruff defaults

by [Tim Hopper](/about/) · [ Markdown ](https://pydevtools.com/handbook/how-to/how-to-configure-recommended-ruff-defaults.md)

[Ruff](/handbook/topics/ruff/)

This guide assumes you have a Python project set up. If you haven't created a project yet, see the [project creation tutorial](https://pydevtools.com/handbook/tutorial/create-your-first-python-project/) before proceeding.

This guide shows how to configure [Ruff](https://pydevtools.com/handbook/reference/ruff/) with a curated set of linting rules that extend beyond the defaults. When starting a new project, it's easier to enable a comprehensive set of rules from the beginning and selectively disable any that don't fit the project's needs, rather than gradually adding rules later when there's already code to fix.

## Adding the Configuration

This guide uses `extend-select` to add rules on top of Ruff's built-in defaults. This differs from migrating existing projects, which typically use `select` to replace the defaults entirely and match the old tool's behavior. For new projects, `extend-select` is simpler because you inherit Ruff's curated baseline instead of specifying every rule category.

Add the following to the project's `pyproject.toml` file:
    
    
    [tool.ruff.lint]
    extend-select = [
        "F",        # Pyflakes rules
        "W",        # PyCodeStyle warnings
        "E",        # PyCodeStyle errors
        "I",        # Sort imports properly
        "UP",       # Warn if certain things can changed due to newer Python versions
        "C4",       # Catch incorrect use of comprehensions, dict, list, etc
        "FA",       # Enforce from __future__ import annotations
        "ISC",      # Good use of string concatenation
        "ICN",      # Use common import conventions
        "RET",      # Good return practices
        "SIM",      # Common simplification rules
        "TID",      # Some good import practices
        "TC",       # Enforce importing certain types in a TYPE_CHECKING block
        "PTH",      # Use pathlib instead of os.path
        "TD",       # Be diligent with TODO comments
        "NPY",      # Some numpy-specific things
        "FURB",     # Suggest more idiomatic Python patterns
    ]

## Running the Linter

Check the project for issues:
    
    
    uv run ruff check .

Automatically fix violations where possible:
    
    
    uv run ruff check --fix .

## Understanding the Rule Categories

### [Pyflakes (F)](https://docs.astral.sh/ruff/rules/#pyflakes-f)

Detects logical errors that would cause runtime failures, including undefined variables, unused imports, and invalid string formatting.

### [PyCodeStyle Errors (E)](https://docs.astral.sh/ruff/rules/#error-e) and [Warnings (W)](https://docs.astral.sh/ruff/rules/#warning-w)

Enforces [PEP 8](https://pydevtools.com/handbook/explanation/what-is-pep-8/) conventions, catching indentation errors, incorrect comparisons (`if x == None`), and whitespace issues.

### [Import Sorting (I)](https://docs.astral.sh/ruff/rules/#isort-i)

Ensures imports follow a consistent ordering convention, grouping standard library, third-party, and local imports predictably.

### [Python Upgrades (UP)](https://docs.astral.sh/ruff/rules/#pyupgrade-up)

Modernizes code syntax to use newer Python features, suggesting f-strings over older formatting and updated type hint syntax.

### [Comprehensions (C4)](https://docs.astral.sh/ruff/rules/#flake8-comprehensions-c4)

Identifies inefficient iteration patterns, flagging unnecessary list comprehensions wrapped in constructors and suggesting simpler alternatives.

### [Future Annotations (FA)](https://docs.astral.sh/ruff/rules/#flake8-future-annotations-fa)

Encourages adding `from __future__ import annotations`, which simplifies forward references in type hints and reduces runtime overhead.

### [String Concatenation (ISC)](https://docs.astral.sh/ruff/rules/#flake8-implicit-str-concat-isc)

Detects implicit string concatenation of adjacent literals, making concatenation explicit and preventing bugs from missing commas.

### [Import Conventions (ICN)](https://docs.astral.sh/ruff/rules/#flake8-import-conventions-icn)

Enforces standard import aliases (`numpy` as `np`, `pandas` as `pd`, `matplotlib.pyplot` as `plt`).

### [Return Practices (RET)](https://docs.astral.sh/ruff/rules/#flake8-return-ret)

Improves function return patterns by flagging unnecessary `return None` statements and suggesting removal of superfluous else blocks.

### [Simplifications (SIM)](https://docs.astral.sh/ruff/rules/#flake8-simplify-sim)

Suggests more elegant code patterns, including combined `isinstance()` checks, natural comparison order, and cleaner boolean logic.

### [Tidy Imports (TID)](https://docs.astral.sh/ruff/rules/#flake8-tidy-imports-tid)

Manages import quality by encouraging absolute imports and helping establish import conventions.

### [Type Checking Imports (TC)](https://docs.astral.sh/ruff/rules/#flake8-type-checking-tc)

Optimizes type-only imports by moving them into `if TYPE_CHECKING:` blocks, reducing import overhead while maintaining type-checking capability.

### [Pathlib Usage (PTH)](https://docs.astral.sh/ruff/rules/#flake8-use-pathlib-pth)

Recommends `pathlib.Path` over `os.path` functions for more object-oriented, cross-platform file handling.

### [TODO Discipline (TD)](https://docs.astral.sh/ruff/rules/#flake8-todos-td)

Enforces conventions for TODO comments, requiring proper formatting and meaningful descriptions.

### [NumPy Conventions (NPY)](https://docs.astral.sh/ruff/rules/#numpy-specific-rules-npy)

Flags deprecated NumPy type aliases and APIs, guiding migration to modern NumPy patterns.

### [Refurb (FURB)](https://docs.astral.sh/ruff/rules/#refurb-furb)

Suggests more idiomatic Python patterns, such as replacing set-add loops with `set.update()`, using `str.removeprefix()` instead of hand-rolled slicing, rewriting conditional expressions as `min()`/`max()` calls, and replacing `open()`/`read()` with `Path.read_text()`. All FURB rules include auto-fix support.

## Selective Rule Disabling

To disable specific rules that conflict with existing practices, add them to the `ignore` list:
    
    
    [tool.ruff.lint]
    extend-select = [
        # ... rules from above
    ]
    ignore = [
        "TD003",  # Example: disable missing TODO link requirement
    ]

Was this helpful?

Thanks for the signal!

What could be improved?

No thanks

Send feedback

## Mentioned in

  * [Ruff: A Complete Guide to Python's Fastest Linter and Formatter](/handbook/explanation/ruff-complete-guide/)
  * [Ruff Already Rewrites Your Python to Be More Idiomatic](/blog/ruff-already-rewrites-your-python-to-be-more-idiomatic/)
  * [uv format: Code Formatting Comes to uv (experimentally!)](/blog/uv-format-code-formatting-comes-to-uv-experimentally/)
  * [Build and Publish a Python Package with uv, Ruff, ty, pytest, and GitHub Actions](/handbook/tutorial/build-and-publish-a-python-package/)
  * [How do Ruff and Pylint compare?](/handbook/explanation/how-do-ruff-and-pylint-compare/)
  * [How to configure Cursor for Ruff](/handbook/how-to/how-to-configure-cursor-for-ruff/)
  * [How to configure Ruff for Django](/handbook/how-to/how-to-configure-ruff-for-django/)
  * [How to configure Ruff with Claude Code](/handbook/how-to/how-to-configure-ruff-with-claude-code/)

Show 9 more

  * [How to Disable Ruff Rules for a Block of Code](/handbook/how-to/how-to-disable-ruff-rules-for-a-block-of-code/)
  * [How to Enable Ruff Security Rules](/handbook/how-to/how-to-enable-ruff-security-rules/)
  * [How to migrate from Black to Ruff formatter](/handbook/how-to/how-to-migrate-from-black-to-ruff-formatter/)
  * [How to replace Black, isort, flake8, and pyupgrade with Ruff](/handbook/how-to/how-to-replace-black-isort-flake8-pyupgrade-with-ruff/)
  * [How to set up pre-commit hooks for a Python project](/handbook/how-to/how-to-set-up-pre-commit-hooks-for-a-python-project/)
  * [How to sort Python imports with Ruff](/handbook/how-to/how-to-sort-python-imports-with-ruff/)
  * [Ruff: Python Linter and Formatter](/handbook/reference/ruff/)
  * [Set up Ruff for formatting and checking your code](/handbook/tutorial/set-up-ruff-for-formatting-and-checking-your-code/)
  * [What is PEP 8?](/handbook/explanation/what-is-pep-8/)



## Get new Python tooling articles in your inbox

One email a month. No spam. Unsubscribe in one click.

Subscribe

Last updated on June 12, 2026

[How to configure PyCharm for a uv project](/handbook/how-to/how-to-configure-pycharm-for-a-uv-project/ "How to configure PyCharm for a uv project")[How to configure Ruff for Django](/handbook/how-to/how-to-configure-ruff-for-django/ "How to configure Ruff for Django")

Please submit corrections and feedback...

Send
