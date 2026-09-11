from fastapi import FastAPI

app = FastAPI(
    title="Smart Waste Management API",
    version="1.0.0"
)


@app.get("/")
def home():
    return {
        "message": "Smart Waste Management API is running"
    }