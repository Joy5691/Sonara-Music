"""
Sonara Music ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Python API Server
Wraps ytmusicapi to provide search, browse, charts, and audio streaming
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse
import yt_dlp
from ytmusicapi import YTMusic
import uvicorn
import os

app = FastAPI(
    title="Sonara Music API",
    description="Backend API powered by ytmusicapi for Sonara Music",
    version="1.0.0",
)

# CORS ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â allow web frontend
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
# AUDIO STREAM URL (via yt-dlp)
# ============================================
from fastapi import Request
import httpx

@app.get("/api/stream_direct/{video_id}")
async def get_stream_direct(video_id: str, request: Request):
    url = extract_stream_url_internal(video_id)
    if not url:
        raise HTTPException(status_code=404, detail="No audio stream found")
    
    headers = {}
    if "range" in request.headers:
        headers["range"] = request.headers["range"]
        
    client = httpx.AsyncClient()
    req = client.build_request("GET", url, headers=headers)
    r = await client.send(req, stream=True)
    
    response_headers = {}
    if "accept-ranges" in r.headers:
        response_headers["Accept-Ranges"] = r.headers["accept-ranges"]
    if "content-length" in r.headers:
        response_headers["Content-Length"] = str(r.headers["content-length"])
    if "content-range" in r.headers:
        response_headers["Content-Range"] = r.headers["content-range"]

    async def generate():
        try:
            async for chunk in r.aiter_bytes():
                yield chunk
        finally:
            await client.aclose()

    return StreamingResponse(
        generate(),
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "audio/mp4"),
        headers=response_headers
    )

import time
STREAM_URL_CACHE = {}

def extract_stream_url_internal(video_id: str):
    now = time.time()
    # Cache for 4 hours (Google Video URLs typically expire in 6 hours)
    if video_id in STREAM_URL_CACHE:
        entry = STREAM_URL_CACHE[video_id]
        if now - entry['timestamp'] < (3600 * 4):
            return entry['url']

    try:
        ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "noplaylist": True,
            "skip_download": True,
            "nocheckcertificate": True,
            "lazy_playlist": True, "extractor_args": {"youtube": {"client": ["mweb", "android"]}},
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Passing just the video ID is sometimes faster than full music URL parsing
            info = ydl.extract_info(video_id, download=False)
            audio_url = None
            if info and "formats" in info:
                audio_formats = [
                    f for f in info["formats"]
                    if f.get("acodec") != "none" and f.get("vcodec") in ("none", None)
                ]
                if audio_formats:
                    audio_formats.sort(key=lambda f: f.get("abr", 0) or 0, reverse=True)
                    audio_url = audio_formats[0]["url"]
            if not audio_url and info:
                audio_url = info.get("url")
            
            if audio_url:
                STREAM_URL_CACHE[video_id] = {
                    'url': audio_url,
                    'timestamp': now
                }
            return audio_url
    except Exception as e:
        return None

@app.get("/api/stream/{video_id}")
def get_stream_url(video_id: str):
    """
    Extract the best audio stream URL for a YouTube video.
    Returns a direct audio URL the frontend can play.
    """
    try:
        ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://music.youtube.com/watch?v={video_id}", download=False
            )
            # Find the best audio-only format
            audio_url = None
            if info and "formats" in info:
                audio_formats = [
                    f for f in info["formats"]
                    if f.get("acodec") != "none" and f.get("vcodec") in ("none", None)
                ]
                if audio_formats:
                    # Sort by audio bitrate descending
                    audio_formats.sort(key=lambda f: f.get("abr", 0) or 0, reverse=True)
                    audio_url = audio_formats[0]["url"]

            if not audio_url and info:
                # Fallback to the url field
                audio_url = info.get("url")

            if not audio_url:
                raise HTTPException(status_code=404, detail="No audio stream found")

            return {
                "success": True,
                "videoId": video_id,
                "title": info.get("title", ""),
                "artist": info.get("artist") or info.get("uploader", ""),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "audioUrl": audio_url,
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stream extraction failed: {str(e)}")


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

