from fastapi import FastAPI

app = FastAPI(title="Job Radar")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
