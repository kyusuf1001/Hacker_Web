from flask import Flask
app = Flask(__name__)

@app.get("/")
def home():
    return "Hello from Render!"

@app.get("/health")
def health():
    return "OK"
