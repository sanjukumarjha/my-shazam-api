from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from shazamio import Shazam
import acoustid
import os
import shutil
import requests
import musicbrainzngs
import mutagen

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURATION ---
ACOUSTID_API_KEY = 'jydFmoPBJ4' # <--- Ensure this is set
# Configure MusicBrainz (Required User Agent)
musicbrainzngs.set_useragent("MyAudioApp", "1.0", "contact@myapp.com")

shazam = Shazam()

def get_cover_art(mbid):
    """Try to fetch cover art from Cover Art Archive"""
    try:
        url = f"http://coverartarchive.org/release/{mbid}/front"
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
        print("Strategy 1: Trying Shazam...")
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

        # --- STRATEGY 2: ACOUSTID (Fingerprint Fallback) ---
        if status == 'no_match':
            print("Strategy 2: Shazam failed. Trying AcoustID...")
            try:
                results = acoustid.match(ACOUSTID_API_KEY, temp_filename, parse=False, meta='recordings releases')
                if results.get('results'):
                    best_match = results['results'][0]
                    if best_match.get('score', 0) > 0.5:
                        rec = best_match.get('recordings', [])[0] if best_match.get('recordings') else None
                        if rec:
                            mbid = rec.get('releases', [{}])[0].get('id')
                            cover_url = get_cover_art(mbid) if mbid else None
                            artist_name = ", ".join([a['name'] for a in rec.get('artists', [])])
                            
                            status = 'matched'
                            metadata = {
                                'title': rec.get('title'),
                                'artist': artist_name,
                                'cover': cover_url,
                                'isrc': None,
                                'link': f"https://musicbrainz.org/recording/{rec['id']}",
                                'label': None,
                                'source': 'AcoustID'
                            }
            except Exception as e:
                print(f"AcoustID error: {e}")

        # --- STRATEGY 3: MUSICBRAINZ TEXT SEARCH (Metadata Fallback) ---
        if status == 'no_match':
            print("Strategy 3: AcoustID failed. Checking File Metadata...")
            try:
                # 1. Read Tags from the file
                audio = mutagen.File(temp_filename, easy=True)
                if audio:
                    # Try to extract Artist and Title
                    # Different formats use different keys, but 'easy=True' standardizes many
                    artist = audio.get('artist', [None])[0]
                    title = audio.get('title', [None])[0]

                    if artist and title:
                        print(f"Found Tags: {artist} - {title}. Searching MusicBrainz...")
                        # 2. Search MusicBrainz Database
                        search_res = musicbrainzngs.search_recordings(artist=artist, recording=title, limit=1)
                        
                        if search_res.get('recording-list'):
                            rec = search_res['recording-list'][0]
                            # Calculate a simple confidence check (exact match preference)
                            if rec['title'].lower() == title.lower():
                                mbid_for_cover = rec.get('release-list', [{}])[0].get('id')
                                cover_url = get_cover_art(mbid_for_cover) if mbid_for_cover else None
                                
                                artist_name = rec.get('artist-credit', [{}])[0].get('artist', {}).get('name', artist)

                                status = 'matched'
                                metadata = {
                                    'title': rec['title'],
                                    'artist': artist_name,
                                    'cover': cover_url,
                                    'isrc': rec.get('isrc-list', [None])[0],
                                    'link': f"https://musicbrainz.org/recording/{rec['id']}",
                                    'label': None,
                                    'source': 'MusicBrainz (Metadata)'
                                }
            except Exception as e:
                print(f"MusicBrainz Search error: {e}")

        return {"status": status, "data": metadata}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
