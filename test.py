import requests
import json
from datetime import datetime
url = "http://127.0.0.1:5000/donate"
data = {
    "date": datetime.now().isoformat(),
    "value": 100.5,
    "name": "Cher_cash"
}
headers = {
    "Content-Type": "application/json"
}

response = requests.post(url, json=data, headers=headers)
print("Статус-код:", response.status_code)
print("Ответ сервера:", response.text)


url = "http://127.0.0.1:5000/balance"
response = requests.get(url)
print("Статус-код:", response.status_code)
print("Ответ сервера:", response.text)