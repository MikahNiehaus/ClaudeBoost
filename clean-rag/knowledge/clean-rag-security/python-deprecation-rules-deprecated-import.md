<!-- Source: https://docs.astral.sh/ruff/rules/deprecated-import/ | Tier: A | Topic: python-deprecation | Fetched: 2026-06-26 -->

Skip to content 

[ ](../.. "Ruff")

Ruff 

deprecated-import (UP035) 

Initializing search 




[ ruff  ](https://github.com/astral-sh/ruff "Go to repository")

[ ](../.. "Ruff") Ruff 

[ ruff  ](https://github.com/astral-sh/ruff "Go to repository")

  * [ Overview  ](../..)
  * [ Tutorial  ](../../tutorial/)
  * [ Installing Ruff  ](../../installation/)
  * [ The Ruff Linter  ](../../linter/)
  * [ The Ruff Formatter  ](../../formatter/)
  * Editors  Editors 
    * [ Editor Integration  ](../../editors/)
    * [ Setup  ](../../editors/setup/)
    * [ Features  ](../../editors/features/)
    * [ Settings  ](../../editors/settings/)
    * [ Migrating from ruff-lsp  ](../../editors/migration/)
  * [ Configuring Ruff  ](../../configuration/)
  * [ Preview  ](../../preview/)
  * [ Rules  ](../)
  * [ Settings  ](../../settings/)
  * [ Versioning  ](../../versioning/)
  * [ Integrations  ](../../integrations/)
  * [ FAQ  ](../../faq/)
  * [ Contributing  ](../../contributing/)



# deprecated-import (UP035)

Added in [v0.0.239](https://github.com/astral-sh/ruff/releases/tag/v0.0.239) · [Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20\(%27deprecated-import%27%20OR%20UP035\)) · [View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fpyupgrade%2Frules%2Fdeprecated_import.rs#L66)

Derived from the **[pyupgrade](../#pyupgrade-up)** linter.

Fix is sometimes available.

## What it does

Checks for uses of deprecated imports based on the minimum supported Python version.

## Why is this bad?

Deprecated imports may be removed in future versions of Python, and should be replaced with their new equivalents.

Note that, in some cases, it may be preferable to continue importing members from `typing_extensions` even after they're added to the Python standard library, as `typing_extensions` can backport bugfixes and optimizations from later Python versions. This rule thus avoids flagging imports from `typing_extensions` in such cases.

## Example
    
    
    from collections import Sequence
    

Use instead:
    
    
    from collections.abc import Sequence
    

Back to top 

Made with [ Material for MkDocs ](https://squidfunk.github.io/mkdocs-material/)

[ ](https://github.com/astral-sh/ruff "github.com") [ ](https://discord.com/invite/astral-sh "discord.com") [ ](https://pypi.org/project/ruff/ "pypi.org") [ ](https://x.com/astral_sh "x.com")
