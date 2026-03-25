from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.orders import router as orders_router
from routes.queue import router as queue_router
from routes.print_routes import router as print_router
from routes.config import router as config_router

app = FastAPI(title="Packing App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orders_router)
app.include_router(queue_router)
app.include_router(print_router)
app.include_router(config_router)


@app.get("/health")
def health():
    return {"status": "ok"}
