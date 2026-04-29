"""Generate a LangGraph workflow visualization for ATLAS.

This script uses the compiled workflow's ``get_graph()`` method so the
diagram stays aligned with ``src.orchestration.workflow.build_workflow``.
"""

from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from src.orchestration.workflow import build_workflow  # noqa: E402


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ATLAS LangGraph Workflow</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f7f8fa;
      color: #1f2933;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
    }}
    header {{
      padding: 24px 32px 12px;
      border-bottom: 1px solid #d9dee7;
      background: #ffffff;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 24px;
      font-weight: 700;
    }}
    p {{
      margin: 0;
      color: #52606d;
      font-size: 14px;
    }}
    main {{
      padding: 24px 32px 32px;
    }}
    .diagram {{
      overflow: auto;
      padding: 24px;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      background: #ffffff;
    }}
    .mermaid {{
      min-width: 760px;
    }}
    details {{
      margin-top: 16px;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      background: #ffffff;
    }}
    summary {{
      cursor: pointer;
      padding: 12px 16px;
      font-weight: 600;
    }}
    pre {{
      margin: 0;
      padding: 16px;
      overflow: auto;
      border-top: 1px solid #d9dee7;
      color: #1f2933;
      background: #fbfcfd;
      font-size: 13px;
      line-height: 1.5;
    }}
  </style>
</head>
<body>
  <header>
    <h1>ATLAS LangGraph Workflow</h1>
    <p>Generated from <code>build_workflow(...).get_graph()</code>. Nodes: {node_count}. Edges: {edge_count}.</p>
  </header>
  <main>
    <section class="diagram">
      <pre class="mermaid">{mermaid}</pre>
    </section>
    <details>
      <summary>Mermaid source</summary>
      <pre>{mermaid}</pre>
    </details>
  </main>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, securityLevel: "loose" }});
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the ATLAS LangGraph workflow via compiled_workflow.get_graph().",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated files. Defaults to the visualization folder.",
    )
    parser.add_argument(
        "--name",
        default="workflow_graph",
        help="Base filename for generated artifacts.",
    )
    parser.add_argument(
        "--no-parallel-search",
        action="store_true",
        help="Build the workflow with parallel search disabled before exporting.",
    )
    parser.add_argument(
        "--ascii",
        action="store_true",
        help="Also write an ASCII rendering of the graph.",
    )
    return parser.parse_args()


def write_html(path: Path, mermaid_source: str, node_count: int, edge_count: int) -> None:
    escaped_mermaid = html.escape(mermaid_source)
    path.write_text(
        HTML_TEMPLATE.format(
            mermaid=escaped_mermaid,
            node_count=node_count,
            edge_count=edge_count,
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    workflow = build_workflow(enable_parallel_search=not args.no_parallel_search)
    graph = workflow.get_graph()
    mermaid_source = graph.draw_mermaid()

    mermaid_path = output_dir / f"{args.name}.mmd"
    html_path = output_dir / f"{args.name}.html"

    mermaid_path.write_text(mermaid_source, encoding="utf-8")
    write_html(
        html_path,
        mermaid_source=mermaid_source,
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
    )

    print(f"Wrote Mermaid: {mermaid_path}")
    print(f"Wrote HTML: {html_path}")

    if args.ascii:
        ascii_path = output_dir / f"{args.name}.txt"
        try:
            ascii_path.write_text(graph.draw_ascii(), encoding="utf-8")
            print(f"Wrote ASCII: {ascii_path}")
        except Exception as exc:
            print(f"Skipped ASCII export: {exc}")


if __name__ == "__main__":
    main()
