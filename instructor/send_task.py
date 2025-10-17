# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests",
# ]
# ///

import requests 


def send_task():
    payload = {
        "email": "student@example.com",
        "secret": "sirjan255",
        "task": "captcha-solver-...",
        "round": 1,
        "nonce": "ab12-...",
        "brief": "Create a captcha solver that handles ?url=https://.../image.png. Default to attached sample.",
        "checks": [
            "Repo has MIT license"
            "README.md is professional",
            "Page displays captcha URL passed at ?url=...",
            "Page displays solved captcha text within 15 seconds",
        ],
        "evaluation_url": "https://webhook.site/5b0a341e-7f92-47e3-96aa-c46c957785bc",
        "attachments": [{ "name": "sample.png", "url": "data:image/png;base64,iVBORw..." }]
        }
    
    response = requests.post("http://localhost:8000/handle_task", json=payload)
    print(response.text)

if __name__ == "__main__":
    send_task()