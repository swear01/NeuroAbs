from openai import OpenAI
import os

api_key = os.environ.get("API_KEY", "")
if not api_key:
    raise RuntimeError("API_KEY is not set.")

client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello"},
    ],
    stream=False
)

print(response.choices[0].message.content)
