import json, sys, subprocess, time

class MCPClient:
    def __init__(self):
        self.p = subprocess.Popen(
            ['npx', '-y', 'chrome-devtools-mcp@latest'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True
        )
        self.msg_id = 1
        self._send_req("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"}
        })
        self._wait_for_response(self.msg_id - 1)

    def _send_req(self, method, params=None):
        req = {"jsonrpc": "2.0", "id": self.msg_id, "method": method}
        if params is not None: req["params"] = params
        self.p.stdin.write(json.dumps(req) + '\n')
        self.p.stdin.flush()
        self.msg_id += 1
        return self.msg_id - 1

    def _wait_for_response(self, req_id):
        while True:
            line = self.p.stdout.readline()
            if not line: return None
            try:
                data = json.loads(line)
                if data.get('id') == req_id:
                    if 'error' in data:
                        print(f"Error: {data['error']}")
                    return data.get('result')
            except:
                pass

    def call_tool(self, name, args):
        req_id = self._send_req("tools/call", {
            "name": name,
            "arguments": args
        })
        return self._wait_for_response(req_id)

def main():
    client = MCPClient()
    print("Navigating...")
    client.call_tool("navigate_page", {"type": "url", "url": "http://127.0.0.1:8001/login"})
    
    time.sleep(1)
    # The UIDs from earlier snapshot were 1_5, 1_6, 1_7.
    # It's better to fetch snapshot again to get fresh uids.
    snap = client.call_tool("take_snapshot", {})
    text = snap['content'][0]['text']
    print(text)
    
    # parse uids
    email_uid = None
    pass_uid = None
    btn_uid = None
    for line in text.split('\n'):
        if 'textbox' in line and 'pitchxai' in line.lower():
            email_uid = line.strip().split(' ')[0][4:]
        elif 'textbox' in line and 'password' in line.lower():
            pass_uid = line.strip().split(' ')[0][4:]
        elif 'button' in line and 'sign in' in line.lower():
            btn_uid = line.strip().split(' ')[0][4:]
            
    print(f"Parsed UIDs: email={email_uid}, pass={pass_uid}, btn={btn_uid}")
    
    if email_uid:
        print("Filling email...")
        client.call_tool("fill", {"uid": email_uid, "value": "dataedge@pitchxai.com"})
    if pass_uid:
        print("Filling password...")
        client.call_tool("fill", {"uid": pass_uid, "value": "dataedge123"})
    if btn_uid:
        print("Clicking sign in...")
        client.call_tool("click", {"uid": btn_uid})
        
    time.sleep(3)
    print("Taking post-login snapshot...")
    snap2 = client.call_tool("take_snapshot", {})
    print(snap2['content'][0]['text'])

if __name__ == '__main__':
    main()
