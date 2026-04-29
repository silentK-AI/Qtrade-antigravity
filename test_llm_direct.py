import requests
import json

api_key = "AIzaSyAng2tHjvA_8WbvONA9U-_7MM7htj2Ki08"
url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}
data = {
    "model": "gemini-2.5-flash",
    "messages": [{"role": "user", "content": "你好，这是测试"}]
}

try:
    resp = requests.post(url, headers=headers, json=data, timeout=10)
    print("Status:", resp.status_code)
    print("Body:", resp.text)
except Exception as e:
    print("Error:", e)
