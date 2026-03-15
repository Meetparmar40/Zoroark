import subprocess
import time

import os

def main():
    env = os.environ.copy()
    env.update({
        "PYTHONUTF8": "1", 
        "PYTHONIOENCODING": "utf-8", 
        "PYTHONPATH": "m:\\Coding\\MCP_Server\\src",
        "CRAWL4AI_LOG_LEVEL": "ERROR",
        "CRAWL4AI_VERBOSE": "False"
    })
    
    p = subprocess.Popen(
        ['m:\\Coding\\MCP_Server\\.venv\\Scripts\\python.exe', '-m', 'mcp_docs_server.main'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env
    )

    req1 = '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}}\n'
    p.stdin.write(req1.encode('utf-8'))
    p.stdin.flush()
    print("Init response:", p.stdout.readline().decode('utf-8').strip())

    req2 = '{"jsonrpc": "2.0", "method": "notifications/initialized"}\n'
    req3 = '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "scrape_page", "arguments": {"url": "https://magicui.design/docs/components/light-rays"}}}\n'
    
    p.stdin.write(req2.encode('utf-8'))
    p.stdin.write(req3.encode('utf-8'))
    p.stdin.flush()

    # Read lines until we find the result or run out
    while True:
        line = p.stdout.readline()
        if not line:
            break
        text = line.decode('utf-8').strip()
        print("STDOUT LINE:", text)
        if '"id": 2' in text or '"id":2' in text:
            break

if __name__ == "__main__":
    main()
