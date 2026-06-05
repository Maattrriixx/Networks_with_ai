
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import NetworkThings    

app = FastAPI()

@app.post("/optimize")
async def optimize_network(request: Request):
    try:
        data = await request.json()
        rooms = data.get("rooms", [])     
        scale = data.get("scale", 0.05)
        eps = data.get("eps", 150)

        if not rooms:
            return JSONResponse(status_code=400, content={"error": "Missing 'rooms' array"})

        result = NetworkThings.run_optimizer(rooms, scale_m_per_px=scale, eps=eps)
        return JSONResponse(content=result)

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})