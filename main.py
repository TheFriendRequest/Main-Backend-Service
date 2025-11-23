from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import composite_router

app = FastAPI(
    title="Composite Backend Service",
    description="Composite service that encapsulates and exposes atomic microservices",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag", "etag", "Location", "Content-Type"]  # Expose ETag header to frontend
)

app.include_router(composite_router.router)

@app.get("/")
def root():
    return {"status": "Composite Backend Service running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

