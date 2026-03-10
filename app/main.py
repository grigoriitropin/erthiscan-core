from fastapi import FastAPI

app = FastAPI # create the fastapi application instance

@app.get("/health") # Define a simple health check endpoint
def health_check():
    return {"status": "ok"}
