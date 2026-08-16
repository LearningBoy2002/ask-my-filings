from fastapi import FastAPI

app = FastAPI(title="Ask My Filings API")


@app.get("/")
async def root() -> dict:
    return {"status": "ok"}