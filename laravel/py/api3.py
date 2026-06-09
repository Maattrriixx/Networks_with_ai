from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import vlan_assigner

app = FastAPI()

@app.post("/assign-vlan")
async def assign_vlan(request: Request):
    try:
        data = await request.json()
        network = data.get('network')
        rooms = data.get('rooms')

        if not network:
            return JSONResponse(status_code=400, content={"error": "Missing 'network' field"})
        if not rooms:
            return JSONResponse(status_code=400, content={"error": "Missing 'rooms' field"})

        enriched_network, stats = vlan_assigner.assign_vlans_and_ips(network, rooms)

        return JSONResponse(content=enriched_network)

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)