from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from shazamio import Shazam
import acoustid
import os
import shutil
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURATION ---
ACOUSTID_API_KEY = 'YOUR_ACOUSTID_KEY_HERE'  # <--- PASTE YOUR KEY HERE

shazam = Shazam()

def get_cover_art(mbid):
    """Try to fetch cover art from Cover Art Archive using MusicBrainz ID"""
    try:
        url = f"http://coverartarchive.org/release/{mbid}/front"
        # Check if it exists (HEAD request)
        r = requests.head(url, allow_redirects=True, timeout=2)
        if r.status_code == 200:
            return r.url
    except:
        pass
    return None

@app.post("/recognize")
async def recognize_audio(file: UploadFile = File(...)):
    temp_filename = f"temp_{file.filename}"
    try:
        # 1. Save File
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        status = 'no_match'
        metadata = None

        # --- STRATEGY 1: SHAZAM (Best for Commercial/Pop) ---
        print("Trying Shazam...")
        try:
            out = await shazam.recognize_song(temp_filename)
            if out and 'track' in out:
                track = out['track']
                status = 'matched'
                metadata = {
                    'title': track.get('title'),
                    'artist': track.get('subtitle'),
                    'cover': track.get('images', {}).get('coverart'),
                    'isrc': track.get('isrc'),
                    'link': track.get('url'),
                    'label': track.get('sections', [{}])[0].get('metadata', [{}])[0].get('text'),
                    'source': 'Shazam'
                }
        except Exception as e:
            print(f"Shazam error: {e}")

        # --- STRATEGY 2: ACOUSTID (Fallback for Files) ---
        if status == 'no_match':
            print("Shazam failed. Trying AcoustID...")
            try:
                # AcoustID lookup (includes recordings and releases to find cover art)
                results = acoustid.match(ACOUSTID_API_KEY, temp_filename, parse=False, meta='recordings releases')
                
                # Check results manually to get the best match
                if results.get('results'):
                    best_match = results['results'][0] # Take the highest score
                    if best_match.get('score', 0) > 0.5: # Only accept good matches
                        recordings = best_match.get('recordings', [])
                        if recordings:
                            rec = recordings[0] # Take first recording
                            
                            # Try to find a release MBID for cover art
                            mbid_for_cover = None
                            if 'releases' in rec:
                                mbid_for_cover = rec['releases'][0]['id']
                            
                            cover_url = get_cover_art(mbid_for_cover) if mbid_for_cover else None
                            
                            artist_name = "Unknown"
                            if 'artists' in rec:
                                artist_name = ", ".join([a['name'] for a in rec['artists']])

                            status = 'matched'
                            metadata = {
                                'title': rec.get('title'),
                                'artist': artist_name,
                                'cover': cover_url, # Fallback cover
                                'isrc': None, # AcoustID rarely has ISRC
                                'link': f"https://musicbrainz.org/recording/{rec['id']}",
                                'label': None,
                                'source': 'AcoustID'
                            }
            except Exception as e:
                print(f"AcoustID error: {e}")

        return {"status": status, "data": metadata}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
