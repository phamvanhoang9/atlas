import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.master.langgraph_agent import LangGraphResearcher


print("Creating LangGraph workflow visualization...")
researcher = LangGraphResearcher(query="test", report_type="research_report")
workflow = researcher.workflow

try:
    # Generate the graph as PNG
    graph_image = workflow.get_graph().draw_mermaid_png()
    
    # Save to file
    output_path = os.path.join(os.path.dirname(__file__), 'workflow_graph.png')
    with open(output_path, 'wb') as f:
        f.write(graph_image)
    
    print(f"✓ Workflow graph saved to: {output_path}")
    print("\nOpening image...")
    
    # Open the image with default viewer
    if os.name == 'nt':  # Windows
        os.startfile(output_path)
    elif os.name == 'posix':  # macOS/Linux
        os.system(f'open "{output_path}" || xdg-open "{output_path}"')
    
    print("✓ Image opened in default viewer")
    
except Exception as e:
    print(f"✗ Error generating graph: {e}")
    print("\nNote: This requires the 'pygraphviz' or 'graphviz' package.")
    print("Install with: pip install pygraphviz")
    print("Or: pip install graphviz")