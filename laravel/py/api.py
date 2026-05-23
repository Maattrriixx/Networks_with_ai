from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import analyzer      

app = FastAPI()

@app.post("/analyze")
async def analyze_image(file: UploadFile = File(...)):
    try:
        # read the image as bytes
        contents = await file.read()
        # To the analyzer
        result = analyzer.process_image(contents)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})