from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from datetime import datetime
import threading
import os

app = Flask(__name__)
CORS(app)

TMDB_API_KEY = "29dfffa9ae088178fa088680b67ce583"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

comedy_movies_cache = []

def fetch_comedy_movies():
    global comedy_movies_cache
    print("[CACHE] Fetching comedy OTT movies...")

    today = datetime.now().strftime("%Y-%m-%d")
    movies = []
    seen_ids = set()

    for page in range(1, 10000):  # no cap, until TMDB runs out
        print(f"[INFO] Checking page {page}")
        params = {
            "api_key": TMDB_API_KEY,
            "with_genres": "35",  # genre 35 = Comedy
            "sort_by": "popularity.desc",
            "release_date.lte": today,
            "page": page
        }

        try:
            response = requests.get(f"{TMDB_BASE_URL}/discover/movie", params=params)
            data = response.json()
            results = data.get("results", [])
            if not results:
                break

            for movie in results:
                movie_id = movie.get("id")
                if not movie_id or movie_id in seen_ids:
                    continue

                # Check OTT availability
                providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"
                prov_response = requests.get(providers_url, params={"api_key": TMDB_API_KEY})
                prov_data = prov_response.json()

                if "results" in prov_data and any("flatrate" in x for x in prov_data["results"].values()):
                    # Get IMDb ID
                    ext_url = f"{TMDB_BASE_URL}/movie/{movie_id}/external_ids"
                    ext_response = requests.get(ext_url, params={"api_key": TMDB_API_KEY})
                    ext_data = ext_response.json()
                    imdb_id = ext_data.get("imdb_id")

                    if imdb_id and imdb_id.startswith("tt"):
                        movie["imdb_id"] = imdb_id
                        movies.append(movie)
                        seen_ids.add(movie_id)

        except Exception as e:
            print(f"[ERROR] Failed at page {page}: {e}")
            break

    comedy_movies_cache = movies
    print(f"[CACHE] Fetched {len(comedy_movies_cache)} comedy movies ✅")

def to_stremio_meta(movie):
    try:
        return {
            "id": movie["imdb_id"],
            "type": "movie",
            "name": movie["title"],
            "poster": f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get("poster_path") else None,
            "description": movie.get("overview", ""),
            "releaseInfo": movie.get("release_date", ""),
            "background": f"https://image.tmdb.org/t/p/w780{movie['backdrop_path']}" if movie.get("backdrop_path") else None
        }
    except Exception as e:
        print(f"[ERROR] Meta convert failed: {e}")
        return None

@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.comedy.catalog",
        "version": "1.0.0",
        "name": "Comedy",
        "description": "Comedy movies from all languages on OTT platforms",
        "resources": ["catalog"],
        "types": ["movie"],
        "catalogs": [{
            "type": "movie",
            "id": "comedy",
            "name": "Comedy"
        }],
        "idPrefixes": ["tt"]
    })

@app.route("/catalog/movie/comedy.json")
def catalog():
    print("[INFO] Comedy catalog requested")
    metas = [to_stremio_meta(m) for m in comedy_movies_cache if to_stremio_meta(m)]
    print(f"[INFO] Returning {len(metas)} movies ✅")
    return jsonify({"metas": metas})

@app.route("/refresh")
def refresh():
    def do_refresh():
        try:
            fetch_comedy_movies()
            print("[REFRESH] Done")
        except Exception as e:
            import traceback
            print(f"[REFRESH ERROR] {traceback.format_exc()}")

    threading.Thread(target=do_refresh).start()
    return jsonify({"status": "refresh started"})

# Initial fetch
fetch_comedy_movies()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
