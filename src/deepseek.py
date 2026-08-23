from openai import OpenAI

client = OpenAI(
    api_key="local-gateway",
    base_url="http://127.0.0.1:35001/v1",
)

response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello"},
    ],
    stream=False
)

print(response.choices[0].message.content)
