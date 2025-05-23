from flask import Flask, jsonify
from flask_cors import CORS
import requests
from datetime import datetime

app = Flask(__name__)
CORS(app)

TMDB_API_KEY = "29dfffa9ae088178fa088680b67ce583"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Global movie cache
feel_good_cache = []

def fetch_feel_good_movies():
    global feel_good_cache
    print("[CACHE] Fetching Feel Good OTT movies...")

    today = datetime.now().strftime("%Y-%m-%d")
    collected = []

    for page in range(1, 1000):
        print(f"[INFO] Checking page {page}")
        params = {
            "api_key": TMDB_API_KEY,
            "sort_by": "popularity.desc",
            "release_date.lte": today,
            "page": page
        }

        try:
            response = requests.get(f"{TMDB_BASE_URL}/discover/movie", params=params)
            results = response.json().get("results", [])
            if not results:
                break

            for movie in results:
                title = movie.get("title", "").lower()
                overview = movie.get("overview", "").lower()
                keywords = ["feel good", "heartwarming", "uplifting", "inspiring", "family", "hope", "joy", "positive"]
                if any(kw in title or kw in overview for kw in keywords):
                    movie_id = movie.get("id")
                    if not movie_id:
                        continue

                    # Check OTT availability
                    providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"
                    prov_response = requests.get(providers_url, params={"api_key": TMDB_API_KEY})
                    prov_data = prov_response.json()

                    if "results" in prov_data and any("flatrate" in v for v in prov_data["results"].values()):
                        ext_url = f"{TMDB_BASE_URL}/movie/{movie_id}/external_ids"
                        ext_response = requests.get(ext_url, params={"api_key": TMDB_API_KEY})
                        ext_data = ext_response.json()
                        imdb_id = ext_data.get("imdb_id")

                        if imdb_id and imdb_id.startswith("tt"):
                            movie["imdb_id"] = imdb_id
                            collected.append(movie)
        except Exception as e:
            print(f"[ERROR] Page {page} failed: {e}")
            break

    # Deduplicate
    seen = set()
    feel_good_cache = []
    for m in collected:
        imdb = m.get("imdb_id")
        if imdb and imdb not in seen:
            seen.add(imdb)
            feel_good_cache.append(m)

    print(f"[CACHE] Fetched {len(feel_good_cache)} Feel Good movies ✅")

def to_stremio_meta(movie):
    try:
        imdb_id = movie.get("imdb_id")
        title = movie.get("title")
        if not imdb_id or not title:
            return None

        return {
            "id": imdb_id,
            "type": "movie",
            "name": title,
            "poster": f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get("poster_path") else None,
            "description": movie.get("overview", ""),
            "releaseInfo": movie.get("release_date", ""),
            "background": f"https://image.tmdb.org/t/p/w780{movie['backdrop_path']}" if movie.get("backdrop_path") else None
        }
    except Exception as e:
        print(f"[ERROR] to_stremio_meta failed: {e}")
        return None

@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.feelgood.catalog",
        "version": "1.0.0",
        "name": "Feel Good",
        "description": "Feel Good and Heartwarming Movies Available on OTT",
        "resources": ["catalog"],
        "types": ["movie"],
        "catalogs": [{
            "type": "movie",
            "id": "feelgood",
            "name": "Feel Good"
        }],
        "idPrefixes": ["tt"]
    })

@app.route("/catalog/movie/feelgood.json")
def catalog():
    print("[INFO] Catalog requested")
    try:
        metas = [meta for meta in (to_stremio_meta(m) for m in feel_good_cache) if meta]
        return jsonify({"metas": metas})
    except Exception as e:
        print(f"[ERROR] Catalog error: {e}")
        return jsonify({"metas": []})

@app.route("/refresh")
def refresh():
    try:
        fetch_feel_good_movies()
        return jsonify({"status": "refreshed", "count": len(feel_good_cache)})
    except Exception as e:
        return jsonify({"error": str(e)})

# Initial load
fetch_feel_good_movies()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000)
