import requests
import json

url = "https://streetweb-news-bot.onrender.com/api/post-now"
headers = {"Content-Type": "application/json"}
data = {"network": "facebook"}

response = requests.post(url, headers=headers, data=json.dumps(data))
print("Status:", response.status_code)
print("Response:", response.text)