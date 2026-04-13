import logging
import os

from langchain_core.tools import tool
from notion_client import Client

log = logging.getLogger(__name__)

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(auth=os.environ["NOTION_TOKEN"])
    return _client


@tool
def create_notion_page(title: str, markdown_content: str, emoji: str = "") -> str:
    """Create a new Notion page under the configured parent page.
    title: The page title
    markdown_content: Body content as simple markdown text
    emoji: Optional emoji icon for the page
    """
    parent_id = os.environ.get("NOTION_PARENT_PAGE_ID", "")
    if not parent_id:
        return "Error: NOTION_PARENT_PAGE_ID is not set. Cannot create page."

    client = _get_client()
    kwargs: dict = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": [{"text": {"content": title}}],
        },
    }
    if emoji:
        kwargs["icon"] = {"type": "emoji", "emoji": emoji}
    if markdown_content:
        kwargs["children"] = _markdown_to_blocks(markdown_content)

    log.info("Creating Notion page '%s'", title)
    page = client.pages.create(**kwargs)
    page_url = page.get("url", "unknown")
    return f"Created page '{title}': {page_url}"


@tool
def search_notion(query: str) -> str:
    """Search Notion for pages matching the query.
    query: search text, e.g. "meeting notes"
    Returns a list of matching page titles and IDs.
    """
    client = _get_client()
    results = client.search(query=query, page_size=5)
    pages = results.get("results", [])
    if not pages:
        return f"No results found for '{query}'."

    lines = []
    for page in pages:
        props = page.get("properties", {})
        title_prop = props.get("title", {})
        if isinstance(title_prop, dict):
            title_arr = title_prop.get("title", [])
        else:
            title_arr = []
        title = title_arr[0]["plain_text"] if title_arr else "Untitled"
        page_id = page["id"]
        lines.append(f"- {title} (ID: {page_id})")
    return "Found pages:\n" + "\n".join(lines)


@tool
def add_content_to_page(page_id: str, markdown_content: str) -> str:
    """Append content to an existing Notion page.
    page_id: The UUID of the page to add content to
    markdown_content: Content as simple markdown text
    """
    client = _get_client()
    blocks = _markdown_to_blocks(markdown_content)
    log.info("Appending %d blocks to page %s", len(blocks), page_id)
    client.blocks.children.append(block_id=page_id, children=blocks)
    return f"Added content to page {page_id}."


def _markdown_to_blocks(md: str) -> list[dict]:
    """Convert simple markdown to Notion block objects."""
    blocks: list[dict] = []
    for line in md.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            blocks.append(_heading(stripped[4:], "heading_3"))
        elif stripped.startswith("## "):
            blocks.append(_heading(stripped[3:], "heading_2"))
        elif stripped.startswith("# "):
            blocks.append(_heading(stripped[2:], "heading_1"))
        elif stripped.startswith("- [ ] ") or stripped.startswith("- [x] "):
            checked = stripped.startswith("- [x] ")
            text = stripped[6:]
            blocks.append({
                "type": "to_do",
                "to_do": {
                    "rich_text": [{"type": "text", "text": {"content": text}}],
                    "checked": checked,
                },
            })
        elif stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append({
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": stripped[2:]}}],
                },
            })
        elif stripped.startswith("---"):
            blocks.append({"type": "divider", "divider": {}})
        else:
            blocks.append(_paragraph(stripped))
    return blocks


def _heading(text: str, level: str) -> dict:
    return {
        "type": level,
        level: {
            "rich_text": [{"type": "text", "text": {"content": text}}],
        },
    }


def _paragraph(text: str) -> dict:
    return {
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": text}}],
        },
    }
