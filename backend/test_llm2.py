import json
import urllib.request as request
import urllib.error

url = 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'
payload = {
    'model': 'doubao-seed-2-0-lite-260215',
    'messages': [{'role': 'user', 'content': 'hello'}]
}
data = json.dumps(payload).encode('utf-8')
req_obj = request.Request(
    url=url,
    data=data,
    headers={
        'Authorization': 'Bearer eaeda6d7-8004-4b1b-80ae-c207b06b84e4',
        'Content-Type': 'application/json'
    },
    method='POST'
)

try:
    with request.urlopen(req_obj, timeout=60) as resp:
        print("Success:", resp.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('HTTPError:', e.read().decode('utf-8'))
except Exception as e:
    print('Other error:', str(e))
