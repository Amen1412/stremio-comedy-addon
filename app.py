from flask import Flask, jsonify
from flask_cors import CORS
import requests
from datetime import datetime

app = Flask(__name__)
CORS(app)

TMDB_API_KEY = "29dfffa9ae088178fa088680b67ce583"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

all_movies_cache = []

def fetch_and_cache_movies():
    global all_movies_cache
    print("[CACHE] Fetching feel-good movies...")

    today = datetime.now().strftime("%Y-%m-%d")
    final_movies = []
    seen_ids = set()

    page = 1
    while len(final_movies) < 1000:
        print(f"[INFO] Checking page {page}")
        params = {
            "api_key": TMDB_API_KEY,
            "sort_by": "popularity.desc",
            "release_date.lte": today,
            "with_keywords": "180547",  # keyword for "feel-good"
            "without_genres": "16,10751",  # Exclude animation, family
            "page": page
        }

        try:
            response = requests.get(f"{TMDB_BASE_URL}/discover/movie", params=params)
            response.raise_for_status()
            results = response.json().get("results", [])
            if not results:
                break

            for movie in results:
                if len(final_movies) >= 1000:
                    break

                movie_id = movie.get("id")
                title = movie.get("title")
                if not movie_id or not title or movie_id in seen_ids:
                    continue

                providers_url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"
                prov_response = requests.get(providers_url, params={"api_key": TMDB_API_KEY})
                prov_data = prov_response.json()

                if "results" in prov_data and "IN" in prov_data["results"]:
                    if "flatrate" in prov_data["results"]["IN"]:
                        ext_url = f"{TMDB_BASE_URL}/movie/{movie_id}/external_ids"
                        ext_response = requests.get(ext_url, params={"api_key": TMDB_API_KEY})
                        ext_data = ext_response.json()
                        imdb_id = ext_data.get("imdb_id")

                        if imdb_id and imdb_id.startswith("tt"):
                            movie["imdb_id"] = imdb_id
                            final_movies.append(movie)
                            seen_ids.add(movie_id)

        except Exception as e:
            print(f"[ERROR] Page {page} failed: {e}")
            break

        page += 1

    all_movies_cache.clear()
    all_movies_cache.extend(final_movies)
    print(f"[CACHE] Fetched {len(all_movies_cache)} feel-good movies ✅")


def to_stremio_meta(movie):
    try:
        imdb_id = movie.get("imdb_id")
        title = movie.get("title")
        return {
            "id": imdb_id,
            "type": "movie",
            "name": title,
            "poster": f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get("poster_path") else None,
            "description": movie.get("overview", ""),
            "releaseInfo": movie.get("release_date", ""),
            "background": f"https://image.tmdb.org/t/p/w780{movie.get('backdrop_path')}" if movie.get("backdrop_path") else None
        } if imdb_id and title else None
    except Exception as e:
        print(f"[ERROR] Meta conversion failed: {e}")
        return None


@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.feelgood.catalog",
        "version": "1.0.0",
        "name": "Feel-Good Movies",
        "description": "Feel-Good Heartwarming Movies on OTT",
        "resources": ["catalog"],
        "types": ["movie"],
        "catalogs": [{
            "type": "movie",
            "id": "feelgood",
            "name": "Feel-Good Movies"
        }],
        "idPrefixes": ["tt"]
    })


@app.route("/catalog/movie/feelgood.json")
def catalog():
    print("[INFO] Catalog requested")
    try:
        metas = [meta for meta in (to_stremio_meta(m) for m in all_movies_cache) if meta]
        print(f"[INFO] Returning {len(metas)} feel-good movies ✅")
        return jsonify({"metas": metas})
    except Exception as e:
        print(f"[ERROR] Catalog error: {e}")
        return jsonify({"metas": []})


@app.route("/refresh")
def refresh():
    try:
        fetch_and_cache_movies()
        return jsonify({"status": "refreshed", "count": len(all_movies_cache)})
    except Exception as e:
        return jsonify({"error": str(e)})


fetch_and_cache_movies()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000)
