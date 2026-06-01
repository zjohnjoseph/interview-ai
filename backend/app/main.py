from fastapi import FastAPI

app = FastAPI(title="Interview AI Core")


@app.get("/")
def read_root():
    return {"status": "healthy", "service": "interview-ai"}