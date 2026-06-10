from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
import NetworkPhysical
import uvicorn

app = FastAPI()

@app.post("/optimize")
async def optimize(
    rooms: list = Body(default=[]),
    scale: float = Body(default=0.05)
):
    try:
        if not rooms:
            return JSONResponse(status_code=400, content={'error': 'Missing rooms array'})

        # تم تثبيت الـ eps هنا برقم 150 واستدعاء الخوارزمية بشكل صحيح
        result = NetworkPhysical.run_optimizer(rooms, scale, eps=150)
        return JSONResponse(content=result)

    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})


if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=80222)