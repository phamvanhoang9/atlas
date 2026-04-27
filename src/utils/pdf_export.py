import aiofiles 
# aiofiles allows for file reading and writing operations to be performed without blocking the asynchronous event loop, while is particularly useful in asynchronous programming paradigms.
import logging
import urllib 
# urllib allows us to interact with and manipulate URLs, perform HTTP requests, handle errors, and parse data from the internet. 
import uuid
from datetime import datetime
# uuid is used for identifying objects, ensuring uniqueness across different systems, sessions, or for any feature that requires unique identifiers.
import markdown
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # PyMuPDF


logger = logging.getLogger(__name__)


def _extract_title(markdown_text: str) -> str:
    for line in markdown_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "ATLAS Research Report"


def _build_table_of_contents(markdown_text: str) -> str:
    items = []
    for line in markdown_text.splitlines():
        if line.startswith("## "):
            items.append((2, line[3:].strip()))
        elif line.startswith("### "):
            items.append((3, line[4:].strip()))

    if not items:
        return ""

    rows = []
    for level, title in items[:18]:
        class_name = "toc-level-3" if level == 3 else "toc-level-2"
        rows.append(f'<li class="{class_name}">{title}</li>')
    return f"""
    <section class="toc">
      <h2>Mục lục</h2>
      <ol>
        {''.join(rows)}
      </ol>
    </section>
    """


async def write_to_file(filename: str, text: str) -> None:
    """Asynchronously write text to a file in UTF-8 encoding.

    Args:
        filename (str): The filename to write to.
        text (str): The text to write.
    """
    # Convert text to UTF-8, replacing any problematic characters
    text_utf8 = text.encode('utf-8', errors='replace').decode('utf-8')

    async with aiofiles.open(filename, "w", encoding='utf-8') as file:
        await file.write(text_utf8)

async def write_md_to_pdf(text: str) -> str:
    """Converts Markdown text to a PDF file and returns the file path.

    Args:
        text (str): Markdown text to convert.

    Returns:
        str: The encoded file path of the generated PDF.
    """
    task = uuid.uuid4().hex
    file_path = f"outputs/{task}"
    logger.info("PDF export start base_path=%s markdown_chars=%s", file_path, len(text))
    await write_to_file(f"{file_path}.md", text)
    logger.info("Markdown report written path=%s.md", file_path)

    try:
        if fitz is None:
            logger.warning("PyMuPDF not installed. Skipping PDF generation.")
            # Return just the markdown file path
            encoded_file_path = urllib.parse.quote(f"{file_path}.md")
            return encoded_file_path
            
        # Convert markdown to HTML
        html_content = markdown.markdown(text, extensions=['extra', 'codehilite', 'tables', 'sane_lists'])
        title = _extract_title(text)
        toc_html = _build_table_of_contents(text)
        generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
        
        # Read CSS file if it exists
        css_content = ""
        try:
            async with aiofiles.open('frontend/pdf_style.css', 'r', encoding='utf-8') as css_file:
                css_content = await css_file.read()
        except FileNotFoundError:
            logger.warning("PDF stylesheet not found; using inline fallback styles")
        
        # Create full HTML document with CSS
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
            {css_content}
            </style>
        </head>
        <body>
            <section class="cover">
                <div class="brand">ATLAS</div>
                <h1>{title}</h1>
                <p class="subtitle">Agentic Research Platform</p>
                <p class="generated-at">Xuất báo cáo: {generated_at}</p>
            </section>
            {toc_html}
            <main class="report-body">
                {html_content}
            </main>
        </body>
        </html>
        """
        
        # Convert HTML to PDF using PyMuPDF
        pdf_document = fitz.open()
        pdf_page = pdf_document.new_page(width=595, height=842)  # A4 size
        
        # Use story to render HTML content with proper margins
        story = fitz.Story(html=full_html)
        writer = fitz.DocumentWriter(f"{file_path}.pdf")
        
        # A4 size with balanced professional report margins.
        margin = 54.0
        a4_rect = fitz.paper_rect("a4")
        content_rect = fitz.Rect(
            a4_rect.x0 + margin,
            a4_rect.y0 + margin,
            a4_rect.x1 - margin,
            a4_rect.y1 - margin
        )
        
        while True:
            device = writer.begin_page(a4_rect)
            more, _ = story.place(content_rect)
            story.draw(device)
            writer.end_page()
            if not more:
                break
        
        writer.close()
        pdf_document.close()
        
        logger.info("PDF report written path=%s.pdf", file_path)
    except (RuntimeError, OSError, ValueError) as exc:
        logger.exception("Error in converting Markdown to PDF: %s", exc)
        # Return markdown file as fallback
        encoded_file_path = urllib.parse.quote(f"{file_path}.md")
        return encoded_file_path

    encoded_file_path = urllib.parse.quote(f"{file_path}.pdf")
    return encoded_file_path
