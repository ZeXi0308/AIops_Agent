
import ericai
client = ericai.EricAI()
    
completion = client.chat.completions.create(
    model="mistralai/Mistral-Small-24B-Instruct-2501",
    messages = [
        {"role": "system", "content": "You are a poetic assistant."},
        {"role": "user", "content": "what time is now."}
    ]
)

print(f"{completion.choices[0].message.content}")
