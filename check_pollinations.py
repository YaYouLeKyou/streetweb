import requests
import re

url = 'https://pollinations.ai/p/Apple?width=1080&height=1080&model=flux'
r = requests.get(url, timeout=20)
print('status=', r.status_code)
print('content-type=', r.headers.get('content-type'))
print('len=', len(r.text))
for m in re.finditer(r'https://[^"\'\s]+\.(jpg|jpeg|png|webp)', r.text):
    print('found=', m.group(0))
