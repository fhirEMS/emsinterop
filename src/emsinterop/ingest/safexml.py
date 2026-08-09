"""Hardened XML parsing — the single entry point for untrusted NEMSIS input.

The push endpoint (`serve.py`) accepts XML from anyone who can reach it, and
lxml's defaults are not safe for that: entity resolution is on, DTDs load, and
there is no expansion limit — the classic XXE / billion-laughs exposure.

Every parse in this package goes through here. Two rules:

  1. The parser resolves no entities, loads no DTDs, and touches no network.
  2. A document carrying ANY doctype is rejected outright. NEMSIS has no
     legitimate DOCTYPE, and rejecting beats merely disabling resolution:
     with resolution off, unresolved entity references become nodes that
     `parser.py` silently skips (its `isinstance(child.tag, str)` guard), which
     would turn an attack into a *silent data drop* — the one thing this
     project's hard rules forbid.

Callers get `etree.XMLSyntaxError` for anything malformed or disallowed, which
`ingest.xsd.validate_dataset` turns into a quarantine record rather than a
crash.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

#: Shared hardened parser. `resolve_entities=False` alone is not enough — see
#: the module docstring for why the doctype check accompanies it.
_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
    dtd_validation=False,
    huge_tree=False,
    recover=False,
)


def _reject_doctype(tree: etree._ElementTree) -> None:
    info = tree.docinfo
    if info.internalDTD is not None or info.externalDTD is not None:
        raise etree.XMLSyntaxError(
            "DOCTYPE is not permitted in NEMSIS input", None, 0, 0, ""
        )


def fromstring(data: bytes | str) -> etree._Element:
    """Parse a document from memory with the hardened parser."""
    if isinstance(data, str):
        data = data.encode()
    root = etree.fromstring(data, parser=_PARSER)
    _reject_doctype(root.getroottree())
    return root


def parse(source: str | Path) -> etree._ElementTree:
    """Parse a document from a path with the hardened parser."""
    tree = etree.parse(str(source), parser=_PARSER)
    _reject_doctype(tree)
    return tree
