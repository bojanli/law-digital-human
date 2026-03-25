import json
import sys
import urllib.request as request
import urllib.error

sys.path.append('app')
from app.core.config import settings

print('API:', settings.resolved_llm_api_key(), 'Model:', settings.resolved_llm_model())

url = settings.resolved_llm_base_url() + '/chat/completions'
payload = {
    'model': settings.resolved_llm_model(),
    'messages': [{'role': 'user', 'content': 'hello'}]
}
data = json.dumps(payload).encode('utf-8')
req_obj = request.Request(
    url=url,
    data=data,
    headers={
        'Authorization': 'Bearer ' + settings.resolved_llm_api_key(),
        'Content-Type': 'application/json'
    },
    method='POST'
)

try:
    with request.urlopen(req_obj, timeout=60) as resp:
        print(resp.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('HTTPError:', e.read().decode('utf-8'))
except Exception as e:
    print('Other error:', str(e))
