from fastapi import FastAPI

app = FastAPI(title="Argo")

@app.get("/health")
def health():
    return {"ok": True}
