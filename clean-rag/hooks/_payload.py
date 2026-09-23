"""Typed reads of an untrusted hook payload, for the hooks that can import them.

Stdin is a system boundary. Every shape that breaks a naive `payload["key"]`
read is still valid JSON: the containing object present but null (so `.get`'s
default never applies) or a string instead of an object, and the field itself a
number or a list rather than a string. Each of those reaches code that assumes
`str` and raises somewhere unrelated -- a non-str `session_id` raises
AttributeError on `.encode()` while being hashed into a record path, and a
non-str report raises AttributeError on `.splitlines()` inside the stamp
parser. Reading them all as "" or {} routes them to the same paths that already
handle a genuinely absent field.

This is the hoist of the `_str_field`/`_dict_field` pair that research-gate.py
and rag-enforce.py each carry a private copy of. Those two copies are
deliberately identical and stay where they are: their filenames are hyphenated
and so cannot be imported, and rewriting them is not part of the change that
created this module. New call sites import from here rather than adding a
third copy.
"""


def str_field(source, key: str) -> str:
    """A string read out of an untrusted payload object, or "" if it isn't one."""
    value = source.get(key) if isinstance(source, dict) else None
    return value if isinstance(value, str) else ""


def dict_field(source, key: str) -> dict:
    """A nested object read out of an untrusted payload object, or {} if it isn't one."""
    value = source.get(key) if isinstance(source, dict) else None
    return value if isinstance(value, dict) else {}
