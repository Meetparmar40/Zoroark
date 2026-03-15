import asyncio
import sys
from mcp_docs_server.pipeline.scraper import scrape_page

async def main():
    try:
        content = await scrape_page('https://magicui.design/docs/components/light-rays')
        with open('scraped_content.txt', 'w', encoding='utf-8') as f:
            f.write(content.get('content', ''))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

asyncio.run(main())
