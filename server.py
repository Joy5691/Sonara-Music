"""
Sonara Music Python API Server
Wraps ytmusicapi to provide search, browse, charts, and audio streaming
"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from ytmusicapi import YTMusic
import uvicorn
import os
import time

app = FastAPI(
    title="Sonara Music API",
    description="Backend API powered by ytmusicapi for Sonara Music",
    version="1.0.0",
)

# CORS - allow web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize ytmusicapi (no auth needed for public data)
ytm = YTMusic()


# ============================================
# HEALTH
# ============================================
@app.get("/health")
def health():
    return {"status": "OK", "message": "Sonara Music API is running"}


# ============================================
# SEARCH
# ============================================
@app.get("/api/search")
def search(
    q: str = Query(..., description="Search query"),
    filter: str = Query(None, description="Filter: songs, videos, albums, artists, playlists"),
    limit: int = Query(20, ge=1, le=50),
):
    """Search YouTube Music for songs, albums, artists, etc."""
    try:
        results = ytm.search(q, filter=filter, limit=limit)
        return {"success": True, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# HOME / BROWSE
# ============================================
@app.get("/api/home")
def get_home(limit: int = Query(6, ge=1, le=20)):
    """Get home page content (trending, recommendations)."""
    try:
        home = ytm.get_home(limit=limit)
        return {"success": True, "sections": home}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# CHARTS
# ============================================
@app.get("/api/charts")
def get_charts(country: str = Query("ZZ", description="Country code, ZZ for global")):
    """Get charts (top songs, trending, top artists, top videos)."""
    try:
        charts = ytm.get_charts(country=country)
        return {"success": True, "charts": charts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# SONG / TRACK INFO
# ============================================
@app.get("/api/song/{video_id}")
def get_song(video_id: str):
    """Get detailed song info by video ID."""
    try:
        song = ytm.get_song(video_id)
        return {"success": True, "song": song}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# ARTIST
# ============================================
@app.get("/api/artist/{channel_id}")
def get_artist(channel_id: str):
    """Get artist page info."""
    try:
        artist = ytm.get_artist(channel_id)
        return {"success": True, "artist": artist}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# ALBUM
# ============================================
@app.get("/api/album/{browse_id}")
def get_album(browse_id: str):
    """Get album info with track listing."""
    try:
        album = ytm.get_album(browse_id)
        return {"success": True, "album": album}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# PLAYLIST
# ============================================
@app.get("/api/playlist/{playlist_id}")
def get_playlist(playlist_id: str, limit: int = Query(100, ge=1, le=500)):
    """Get playlist info with tracks."""
    try:
        playlist = ytm.get_playlist(playlist_id, limit=limit)
        return {"success": True, "playlist": playlist}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# LYRICS
# ============================================
@app.get("/api/lyrics/{browse_id}")
def get_lyrics(browse_id: str):
    """Get lyrics for a song. Use the browseId from watch playlist."""
    try:
        lyrics = ytm.get_lyrics(browse_id)
        return {"success": True, "lyrics": lyrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# WATCH PLAYLIST (get related tracks + lyrics browseId)
# ============================================
@app.get("/api/watch/{video_id}")
def get_watch_playlist(video_id: str, limit: int = Query(25, ge=1, le=50)):
    """Get the watch playlist for a video (up next, related tracks)."""
    try:
        watch = ytm.get_watch_playlist(videoId=video_id, limit=limit)
        return {"success": True, "watch": watch}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# AUDIO STREAM URL (via pytubefix)
# ============================================
STREAM_URL_CACHE = {}


def extract_audio_url(video_id: str):
    """
    Use pytubefix to extract a direct audio stream URL.
    pytubefix bundles its own Node.js runtime and can decrypt
    YouTube's signature cipher, which works from any IP.
    """
    now = time.time()

    # Check cache first (URLs expire after ~6 hours, we cache for 4)
    if video_id in STREAM_URL_CACHE:
        entry = STREAM_URL_CACHE[video_id]
        if now - entry["timestamp"] < (3600 * 4):
            return entry["url"]

    # Try multiple pytubefix clients in order of reliability
    from pytubefix import YouTube

    for client in ["WEB", "WEB_MUSIC", "MWEB", "ANDROID_MUSIC"]:
        try:
            yt = YouTube(
                f"https://www.youtube.com/watch?v={video_id}",
                client=client,
            )
            stream = yt.streams.get_audio_only()
            if stream and stream.url:
                STREAM_URL_CACHE[video_id] = {"url": stream.url, "timestamp": now}
                return stream.url
        except Exception as e:
            print(f"pytubefix client={client} failed for {video_id}: {e}")
            continue

    return None


@app.get("/api/stream_info/{video_id}")
def get_stream_info(video_id: str):
    """
    Returns the direct audio URL as JSON.
    The frontend plays this URL directly in the browser.
    """
    audio_url = extract_audio_url(video_id)
    if not audio_url:
        raise HTTPException(status_code=404, detail="No audio stream found")
    return {"success": True, "audioUrl": audio_url}


@app.get("/api/stream_direct/{video_id}")
async def get_stream_direct(video_id: str, request: Request):
    """Redirect to direct audio URL (backward compat)."""
    audio_url = extract_audio_url(video_id)
    if not audio_url:
        raise HTTPException(status_code=404, detail="No audio stream found")
    return RedirectResponse(url=audio_url, status_code=302)


@app.get("/api/stream/{video_id}")
def get_stream_url(video_id: str):
    """
    Extract the best audio stream URL for a YouTube video.
    Returns a direct audio URL the frontend can play.
    """
    audio_url = extract_audio_url(video_id)
    if not audio_url:
        raise HTTPException(status_code=404, detail="No audio stream found")
    return {
        "success": True,
        "videoId": video_id,
        "audioUrl": audio_url,
    }


# ============================================
# EXPLORE (moods, genres)
# ============================================
@app.get("/api/moods")
def get_moods():
    """Get mood and genre categories."""
    try:
        moods = ytm.get_mood_categories()
        return {"success": True, "moods": moods}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/moods/{params}")
def get_mood_playlists(params: str):
    """Get playlists for a specific mood/genre category."""
    try:
        playlists = ytm.get_mood_playlists(params)
        return {"success": True, "playlists": playlists}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# SUGGESTIONS
# ============================================
@app.get("/api/suggestions")
def get_search_suggestions(q: str = Query(...)):
    """Get search suggestions as you type."""
    try:
        suggestions = ytm.get_search_suggestions(q)
        return {"success": True, "suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
