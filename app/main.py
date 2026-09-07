from fastapi import FastAPI

from app.api.jobs import router as jobs_router

app = FastAPI(title="Job Radar")
app.include_router(jobs_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
