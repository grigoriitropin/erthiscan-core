from fastapi import FastAPI

# create the fastapi application instance
app = FastAPI()

# Define a simple health check endpoint
@app.get("/health")
def health_check():
    return {"status": "ok"}
