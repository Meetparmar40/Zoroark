import sys, os
sys.path.insert(0, r"m:\Coding\MCP_Server\src")
os.chdir(r"m:\Coding\MCP_Server")

results = []

# Test each import step individually
try:
    from mcp_docs_server.config import settings
    results.append("1. config: OK")
except Exception as e:
    results.append(f"1. config: FAIL - {e}")

try:
    from mcp_docs_server.pipeline.resolver import URLResolver
    results.append("2. resolver: OK")
except Exception as e:
    results.append(f"2. resolver: FAIL - {e}")

try:
    from mcp_docs_server.pipeline.scraper import scrape_page
    results.append("3. scraper: OK")
except Exception as e:
    results.append(f"3. scraper: FAIL - {e}")

try:
    from mcp_docs_server.main import mcp
    results.append(f"4. main: OK (server name: {mcp.name})")
except Exception as e:
    results.append(f"4. main: FAIL - {e}")

# Write results to a file for clean reading
with open(r"m:\Coding\MCP_Server\diag_results.txt", "w") as f:
    f.write("\n".join(results))
    
print("\n".join(results))
