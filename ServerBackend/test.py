import requests

url = "http://10.162.176.225:5000/api/iot"

data = {
    "email": "krushna@gmail.com",
    "moisture": 55,
    "ph": 6.5,
    "temperature": 30
}

res = requests.post(url, json=data)
print(res.text)