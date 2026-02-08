from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from shazamio import Shazam
import os
import shutil

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

shazam = Shazam()

@app.post("/recognize")
async def recognize_audio(file: UploadFile = File(...)):
    temp_filename = f"temp_{file.filename}"
    try:
        # 1. Save the uploaded snippet to a temporary file
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 2. Run ShazamIO on the file
        out = await shazam.recognize_song(temp_filename)
        
        # 3. Process Result
        status = 'no_match'
        metadata = None
        
        if out and 'track' in out:
             status = 'matched'
             track = out['track']
             metadata = {
                 'title': track.get('title'),
                 'artist': track.get('subtitle'),
                 'cover': track.get('images', {}).get('coverart'),
                 'isrc': track.get('isrc'),
                 'link': track.get('url'),
                 'label': track.get('sections', [{}])[0].get('metadata', [{}])[0].get('text')
             }
             
        return {"status": status, "data": metadata}

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 4. Cleanup: Delete the temp file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)