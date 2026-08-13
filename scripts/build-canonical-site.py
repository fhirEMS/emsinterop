#!/usr/bin/env python3
"""Generate the static site that serves this project's canonical URLs.

A canonical URL is a promise that something is *there*. We mint ~224 of them —
one per ValueSet, ConceptMap, StructureMap, logical model, the NEMSIS registry
CodeSystem, and the one extension that reaches emitted data — and until this
site exists every one of them 404s. That is the first thing a reviewer notices
and the first thing an implementer curses.

The site is generated from the same builder that produces the released
terminology package, so what resolves at a canonical is exactly what the
package ships. Generating it by hand would guarantee the two drift.

Layout follows the convention published IGs use: HTML at the canonical itself
for a human, and the raw resource at `<canonical>.json` for a tool.

    /fhir/StructureDefinition/ems-obtained-prior-to-unit-care        -> HTML
    /fhir/StructureDefinition/ems-obtained-prior-to-unit-care.json   -> JSON

GitHub Pages sets content-type from the file extension, which is why the JSON
carries one and the HTML lives at `<name>/index.html`.

Usage:  python scripts/build-canonical-site.py site/
"""

from __future__ import annotations

import html
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from emsinterop import conformance  # noqa: E402
from emsinterop.terminology.igpackage import build_package  # noqa: E402

CSS = """
:root { color-scheme: light dark;
  --fg:#111; --muted:#555; --bg:#fff; --line:#d8d8d8; --accent:#0b5; --code:#f4f4f4; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e6e6e6; --muted:#a0a0a0; --bg:#111; --line:#333; --code:#1b1b1b; } }
* { box-sizing:border-box }
body { margin:0 auto; padding:2rem 1.25rem 5rem; max-width:56rem; background:var(--bg);
  color:var(--fg); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
h1 { font-size:1.6rem; margin:0 0 .25rem }
h2 { font-size:1.15rem; margin:2.5rem 0 .75rem; padding-bottom:.3rem; border-bottom:1px solid var(--line) }
a { color:inherit; text-decoration:underline; text-underline-offset:2px }
.muted { color:var(--muted) }
.lede { color:var(--muted); margin:0 0 2rem }
code, pre { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.86em }
pre { background:var(--code); padding:1rem; border-radius:6px; overflow-x:auto; max-width:100% }
table { border-collapse:collapse; width:100%; display:block; overflow-x:auto }
th, td { text-align:left; padding:.5rem .6rem; border-bottom:1px solid var(--line); vertical-align:top }
th { font-size:.78rem; text-transform:uppercase; letter-spacing:.04em; color:var(--muted) }
.k { display:inline-block; padding:.1rem .45rem; border:1px solid var(--line);
  border-radius:999px; font-size:.75rem; color:var(--muted) }
ul.cols { columns:2; gap:2rem; padding-left:1.1rem }
@media (max-width:600px) { ul.cols { columns:1 } }
footer { margin-top:4rem; padding-top:1rem; border-top:1px solid var(--line);
  color:var(--muted); font-size:.85rem }
"""


def page(title: str, body: str, up: str = "") -> str:
    crumb = f'<p class="muted"><a href="{up}">&larr; back</a></p>' if up else ""
    return (
        "<!doctype html><html lang=en><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{CSS}</style>"
        f"{crumb}{body}"
        "<footer>Generated from the <code>emsinterop.nemsis</code> package by "
        "<code>scripts/build-canonical-site.py</code> — what resolves here is "
        "exactly what the package ships.<br>"
        "Synthetic data only. No real patient data is used, produced or implied."
        "</footer></html>"
    )


def artifact_page(resource: dict, rel_json: str, fml_href: str = "") -> str:
    url = resource.get("url", "")
    rows = [
        ("Canonical", f"<code>{html.escape(url)}</code>"),
        ("Resource type", html.escape(resource.get("resourceType", ""))),
        ("Version", html.escape(str(resource.get("version", "")))),
        ("Status", html.escape(str(resource.get("status", "")))),
    ]
    for identifier in resource.get("identifier", []) or []:
        value = identifier.get("value", "") if isinstance(identifier, dict) else ""
        if value:
            rows.append(("Also identified by", f"<code>{html.escape(value)}</code>"))

    description = resource.get("description", "")
    body = [
        f"<h1>{html.escape(resource.get('title') or resource.get('name') or url)}</h1>",
        f'<p class="lede">{html.escape(description)}</p>' if description else "",
        "<table><tbody>",
        *(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows if v),
        "</tbody></table>",
        f'<h2>Machine-readable</h2><p><a href="{rel_json}">{rel_json}</a></p>',
        (f'<p><a href="{fml_href}">{fml_href}</a> — the authored FML source</p>'
         if fml_href else ""),
    ]
    # Concept/element lists get long; a preview beats a 2 MB page.
    preview = dict(resource)
    for bulky in ("concept", "compose", "group", "snapshot", "differential"):
        if bulky in preview and isinstance(preview[bulky], list) and len(preview[bulky]) > 8:
            preview[bulky] = preview[bulky][:8] + [f"... {len(resource[bulky]) - 8} more"]
    body.append("<h2>Preview</h2><pre>"
                + html.escape(json.dumps(preview, indent=2)[:12000]) + "</pre>")
    return page(resource.get("name") or url, "\n".join(body), up="../")


def index_page(by_kind: dict[str, list[dict]]) -> str:
    gaps = conformance.summary()["gaps"]
    body = [
        "<h1>emsInterop — FHIR conformance artifacts</h1>",
        '<p class="lede">Canonical definitions for the NEMSIS&nbsp;v3.5 &rarr; '
        "IHE-conformant FHIR&nbsp;R4 translation engine at "
        '<a href="https://github.com/fhirEMS/emsinterop">github.com/fhirEMS/emsinterop</a>. '
        "Everything here is authored by this project; nothing here redefines an "
        "identifier owned by HL7, IHE, SNOMED or LOINC.</p>",

        "<h2>What is ours and what is not</h2>",
        "<p>The IHE EMS profiles leave much of a working translator undecided, so "
        "this project decides — and says so. Those decisions are <em>not</em> "
        "conformance, and the difference is declared rather than blurred:</p>",
        "<ul>",
        "<li><strong>We reference other people's canonicals, and never publish at "
        "them.</strong> NEMSIS codings point at the mPSC canonical, so this "
        "project's data becomes conformant the day that IG is fixed — with no "
        "migration. Our own registry-derived concepts are published here, under "
        "our own identifier, recording which canonical they stand in for.</li>",
        "<li><strong>Canonical URLs resolve; naming systems need not.</strong> "
        "Identifier schemes such as <code>urn:emsinterop:resource-id</code> name "
        "no document and stay URNs deliberately.</li>",
        "</ul>",

        "<h2>Gap register</h2>",
        "<p>Each entry records what the IHE profiles leave open, what this project "
        "does instead, and — the part usually missing — what makes the local "
        "decision go away. A decision with no retirement trigger is a permanent "
        "fork wearing a temporary label.</p>",
        "<table><thead><tr><th>Gap</th><th>What is open</th><th>What we do</th>"
        "<th>Retires when</th></tr></thead><tbody>",
    ]
    for gap in gaps:
        body.append(
            f"<tr><td><code>{html.escape(gap['id'])}</code><br>"
            f"<span class=muted>verified {html.escape(gap['verified'])}</span></td>"
            f"<td>{html.escape(gap['finding'])}<br>"
            f"<a class=muted href=\"{html.escape(gap['source'])}\">source</a></td>"
            f"<td>{html.escape(gap['decision'])}</td>"
            f"<td>{html.escape(gap['retirement'])}</td></tr>"
        )
    body.append("</tbody></table>")

    for kind in sorted(by_kind):
        entries = sorted(by_kind[kind], key=lambda r: r.get("url", ""))
        body.append(f'<h2>{html.escape(kind)} <span class=k>{len(entries)}</span></h2>')
        body.append('<ul class="cols">')
        for resource in entries:
            name = urlsplit(resource["url"]).path.rsplit("/", 1)[-1]
            body.append(f'<li><a href="fhir/{kind}/{html.escape(name)}/">'
                        f"{html.escape(name)}</a></li>")
        body.append("</ul>")
    return page("emsInterop — FHIR conformance artifacts", "\n".join(body))


def main(out_dir: str) -> int:
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    with tempfile.TemporaryDirectory() as staging:
        build_package(staging)
        resources = []
        for path in sorted(Path(staging).glob("*.json")):
            if path.name == "package.json":
                continue
            resources.append(json.loads(path.read_text()))

    # The repo's authored artifacts that the package does not carry (logical
    # models, StructureMaps) still own canonicals and must resolve too.
    for extra in sorted((REPO / "maps").rglob("*.json")):
        data = json.loads(extra.read_text())
        if isinstance(data, dict) and conformance.is_ours(data.get("url", "")):
            if not any(r.get("url") == data["url"] for r in resources):
                resources.append(data)

    # StructureMaps are authored as FML text, not JSON, so they are not in the
    # package — but they still mint canonicals, and a canonical that 404s is a
    # broken promise regardless of the source format.
    for source in sorted((REPO / "maps" / "structuremaps").glob("*.map")):
        text = source.read_text()
        match = re.search(r'map\s+"([^"]+)"\s*=\s*"([^"]+)"', text)
        if not match or not conformance.is_ours(match.group(1)):
            continue
        resources.append({
            "resourceType": "StructureMap",
            "url": match.group(1),
            "name": match.group(2),
            "status": "draft",
            "description": "Authored in FHIR Mapping Language. Executed "
                           "natively in Python by the mapper; this map is the "
                           "authored spec and a CI-only fidelity oracle.",
            "_fml": text,
        })

    by_kind: dict[str, list[dict]] = {}
    base_path = urlsplit(conformance.CANONICAL_BASE).path.strip("/")
    written = 0
    for resource in resources:
        url = resource.get("url", "")
        if not conformance.is_ours(url):
            continue
        rel = urlsplit(url).path.strip("/")
        assert rel.startswith(base_path + "/"), url
        kind, name = rel[len(base_path) + 1:].split("/", 1)
        by_kind.setdefault(kind, []).append(resource)

        directory = out / base_path / kind / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "index.html").write_text(
            artifact_page(resource, f"../{name}.json",
                          fml_href=f"../{name}.fml" if "_fml" in resource else ""))
        fml = resource.pop("_fml", None)
        if fml is not None:
            # The FML source IS the artifact; a JSON husk of it would be a
            # worse answer to the canonical than the map itself.
            (out / base_path / kind / f"{name}.fml").write_text(fml)
        (out / base_path / kind / f"{name}.json").write_text(
            json.dumps(resource, indent=2) + "\n")
        written += 1

    (out / "index.html").write_text(index_page(by_kind))
    (out / base_path).mkdir(parents=True, exist_ok=True)
    (out / base_path / "index.html").write_text(index_page(by_kind))
    # Pages needs this to serve the custom domain.
    (out / "CNAME").write_text(
        urlsplit(conformance.CANONICAL_BASE).netloc + "\n")
    # Jekyll would otherwise skip files and directories beginning with an
    # underscore, and reprocess our HTML for no reason.
    (out / ".nojekyll").write_text("")

    print(json.dumps({
        "out": str(out),
        "canonicalBase": conformance.CANONICAL_BASE,
        "artifacts": written,
        "byKind": {k: len(v) for k, v in sorted(by_kind.items())},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "site"))
