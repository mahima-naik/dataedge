import json, sys, subprocess, time

def main():
    p = subprocess.Popen(
        ['npx', '-y', 'chrome-devtools-mcp@latest'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True
    )
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"}
        }
    }
    p.stdin.write(json.dumps(req) + '\n')
    p.stdin.flush()
    
    req2 = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list"
    }
    p.stdin.write(json.dumps(req2) + '\n')
    p.stdin.flush()
    
    while True:
        line = p.stdout.readline()
        if not line: break
        try:
            data = json.loads(line)
            if data.get('id') == 2:
                for tool in data.get('result', {}).get('tools', []):
                    print(tool.get('name'))
                break
        except:
            pass

if __name__ == '__main__':
    main()
