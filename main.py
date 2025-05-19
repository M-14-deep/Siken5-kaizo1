#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import requests
import urllib.parse
import datetime
import random
import os

from fastapi import FastAPI, Response, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response as FastAPIResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import yt_dlp

# ----------------------------------------------------------------
# グローバル設定
#
# Piped API は複数のインスタンスを用意できます（例として 2 つ）。
PIPED_INSTANCES = [
    "https://pipedapi1.example.com/api/v2",  # ← ご自身のインスタンス URL に置換
    "https://pipedapi2.example.com/api/v2"
]
# Invidious の API インスタンス（例）
INV_API_BASE = "https://invidious.snopyta.org"

# ----------------------------------------------------------------
# ユーティリティ関数

user_agents = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/94.0.4606.61 Safari/537.36',
]

def getRandomUserAgent():
    return {'User-Agent': random.choice(user_agents)}

def checkCookie(cookie: str):
    """Cookie の値が "True" なら認証済みとみなす"""
    return cookie == "True"


# ----------------------------------------------------------------
# 動画情報取得関数

# 1. yt-dlp を利用する場合
def get_video_data_yt_dlp(videoid: str):
    url = f"https://www.youtube.com/watch?v={videoid}"
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'forcejson': True,
        'simulate': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"yt-dlp error: {e}")
        return None
    video_data = {
        "title": info.get("title", "No Title"),
        "description": info.get("description", "").replace("\n", "<br>"),
        "author": info.get("uploader", "Unknown"),
        "length_text": str(datetime.timedelta(seconds=info.get("duration", 0))),
        "views": info.get("view_count", 0),
        "video_urls": [],
        "thumbnail": info.get("thumbnail", "")
    }
    if "formats" in info:
        # 例として、mp4 かつ progressive なもののみ抽出
        video_data["video_urls"] = [
            fmt.get("url") for fmt in info["formats"]
            if fmt.get("url") and fmt.get("ext") in ("mp4",)
        ]
    return video_data

# 2. Invidious を利用する場合
def get_video_data_inv(videoid: str):
    url = f"{INV_API_BASE}/api/v1/videos/{videoid}"
    try:
        resp = requests.get(url, headers=getRandomUserAgent(), timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception as e:
        print(f"Invidious error: {e}")
        return None
    video_data = {
        "title": data.get("title", "No Title"),
        "description": data.get("descriptionHtml", "").replace("\n", "<br>"),
        "author": data.get("author", "Unknown"),
        "length_text": str(datetime.timedelta(seconds=data.get("lengthSeconds", 0))),
        "views": data.get("viewCount", 0),
        "video_urls": [],
        "thumbnail": ""
    }
    # サムネイルが得られる場合
    thumbnails = data.get("videoThumbnails", [])
    if thumbnails:
        video_data["thumbnail"] = thumbnails[-1].get("url", "")
    if "formatStreams" in data:
        video_data["video_urls"] = list(reversed([
            fmt.get("url") for fmt in data.get("formatStreams", [])
            if fmt.get("url")
        ]))
    return video_data

# 3. Piped を利用する場合（複数のインスタンスから順次トライ）
def get_video_data_piped(videoid: str):
    for instance in PIPED_INSTANCES:
        url = instance + f"/video/{videoid}"
        try:
            resp = requests.get(url, headers=getRandomUserAgent(), timeout=5)
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception as e:
            print(f"Piped error ({instance}): {e}")
            continue
        video_data = {
            "title": data.get("title", "No Title"),
            "description": data.get("description", "").replace("\n", "<br>"),
            "author": data.get("author", "Unknown"),
            "length_text": str(datetime.timedelta(seconds=data.get("duration", 0))),
            "views": data.get("views", 0),
            "video_urls": [],
            "thumbnail": data.get("thumbnail", "")
        }
        if "streams" in data:
            video_data["video_urls"] = [
                stream.get("url") for stream in data.get("streams", [])
                if stream.get("url")
            ]
        return video_data
    return None

# 共通インターフェース：backend パラメータに応じて切り替え
def get_video_data(videoid: str, backend: str = "ytdlp"):
    if backend == "ytdlp":
        return get_video_data_yt_dlp(videoid)
    elif backend == "inv":
        return get_video_data_inv(videoid)
    elif backend == "piped":
        return get_video_data_piped(videoid)
    else:
        return get_video_data_yt_dlp(videoid)


# ----------------------------------------------------------------
# 検索情報取得関数

# yt-dlp による検索 (ytsearch を利用)
def get_search_data_yt_dlp(query: str, max_results: int = 10):
    search_query = f"ytsearch{max_results}:{query}"
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(search_query, download=False)
    except Exception as e:
        print(f"yt-dlp search error: {e}")
        return []
    entries = result.get("entries", [])
    results = []
    for entry in entries:
        results.append({
            "type": "video",
            "title": entry.get("title"),
            "id": entry.get("id"),
            "author": entry.get("uploader"),
            "duration": str(datetime.timedelta(seconds=entry.get("duration", 0))),
            "views": entry.get("view_count", 0)
        })
    return results

# Invidious による検索
def get_search_data_inv(query: str, page: int = 1):
    url = f"{INV_API_BASE}/api/v1/search"
    params = {"q": query, "page": page}
    try:
        resp = requests.get(url, headers=getRandomUserAgent(), params=params, timeout=5)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception as e:
        print(f"Invidious search error: {e}")
        return []
    results = []
    for item in data:
        if item.get("type") == "video":
            results.append({
                "type": "video",
                "title": item.get("title", "No Title"),
                "id": item.get("videoId", ""),
                "author": item.get("author", "Unknown"),
                "duration": str(datetime.timedelta(seconds=item.get("lengthSeconds", 0))),
                "views": item.get("viewCount", 0),
            })
    return results

# Piped による検索（複数の Piped インスタンスから）
def get_search_data_piped(query: str, page: int = 1):
    for instance in PIPED_INSTANCES:
        url = instance + "/search"
        params = {"q": query, "page": page}
        try:
            resp = requests.get(url, headers=getRandomUserAgent(), params=params, timeout=5)
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception as e:
            print(f"Piped search error ({instance}): {e}")
            continue
        results = []
        for item in data.get("results", []):
            if item.get("type") == "video":
                results.append({
                    "type": "video",
                    "title": item.get("title", "No Title"),
                    "id": item.get("videoId", ""),
                    "author": item.get("author", "Unknown"),
                    "duration": str(datetime.timedelta(seconds=item.get("duration", 0))),
                    "views": item.get("views", 0)
                })
        return results
    return []

def get_search_data(query: str, page: int = 1, backend: str = "ytdlp"):
    if backend == "ytdlp":
        return get_search_data_yt_dlp(query)
    elif backend == "inv":
        return get_search_data_inv(query, page)
    elif backend == "piped":
        return get_search_data_piped(query, page)
    else:
        return get_search_data_yt_dlp(query)


# ----------------------------------------------------------------
# FastAPI アプリケーションのセットアップ

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/js", StaticFiles(directory="./statics/js"), name="js")
app.mount("/css", StaticFiles(directory="./statics/css"), name="css")
app.mount("/img", StaticFiles(directory="./statics/img"), name="img")
app.add_middleware(GZipMiddleware, minimum_size=1000)
templates = Jinja2Templates(directory="templates")


# ----------------------------------------------------------------
# エンドポイント

@app.get("/", response_class=HTMLResponse)
def home(response: Response, request: Request, yuki: str = Cookie(default="False")):
    if checkCookie(yuki):
        response.set_cookie("yuki", "True", max_age=60*60*24*7)
        return templates.TemplateResponse("home.html", {"request": request})
    return RedirectResponse(url="/genesis")


# 動画再生エンドポイント (例: /watch?v=動画ID&backend=指定)
@app.get("/watch", response_class=HTMLResponse)
def watch(v: str, backend: str = "ytdlp", response: Response = None, request: Request = None,
          yuki: str = Cookie(default="False"), proxy: str = Cookie(default="")):
    if not checkCookie(yuki):
        return RedirectResponse(url="/")
    response.set_cookie("yuki", "True", max_age=60*60*24*7)
    video_data = get_video_data(v, backend)
    if not video_data:
        return HTMLResponse(content="動画情報の取得に失敗しました", status_code=500)
    # テンプレートは場合に応じて切替可能（例：ume.html と video.html）
    template_name = "ume.html" if request.cookies.get("ume_toggle", "false") == "true" else "video.html"
    return templates.TemplateResponse(template_name, {
        "request": request,
        "videoid": v,
        "videourls": video_data["video_urls"],
        "video_title": video_data["title"],
        "description": video_data["description"],
        "author": video_data["author"],
        "length_text": video_data["length_text"],
        "view_count": video_data["views"],
        "thumbnail": video_data["thumbnail"],
        "backend": backend,
        "proxy": proxy
    })


# 検索エンドポイント (例: /search?q=キーワード&page=1&backend=指定)
@app.get("/search", response_class=HTMLResponse)
def search(q: str, page: int = 1, backend: str = "ytdlp", response: Response = None, request: Request = None,
           yuki: str = Cookie(default="False"), proxy: str = Cookie(default="")):
    if not checkCookie(yuki):
        return RedirectResponse(url="/")
    response.set_cookie("yuki", "True", max_age=60*60*24*7)
    results = get_search_data(q, page, backend)
    next_page = f"/search?q={urllib.parse.quote(q)}&page={page+1}&backend={backend}"
    return templates.TemplateResponse("search.html", {
        "request": request,
        "results": results,
        "word": q,
        "next": next_page,
        "backend": backend,
        "proxy": proxy
    })


# サムネイル (YouTube の公開サムネイル画像)
@app.get("/thumbnail")
def thumbnail(v: str):
    thumbnail_url = f"https://img.youtube.com/vi/{v}/0.jpg"
    try:
        resp = requests.get(thumbnail_url, headers=getRandomUserAgent())
        return FastAPIResponse(content=resp.content, media_type="image/jpeg")
    except Exception as e:
        return FastAPIResponse(content=f"サムネイルの取得に失敗しました: {e}", status_code=500)


# サジェスト（Google のオートコンプリート API をそのまま利用）
@app.get("/suggest")
def suggest(keyword: str):
    try:
        url = "http://www.google.com/complete/search?client=youtube&hl=ja&ds=yt&q=" + urllib.parse.quote(keyword)
        resp = requests.get(url, headers=getRandomUserAgent())
        suggestions = [item[0] for item in json.loads(resp.text[19:-1])[1]]
        return suggestions
    except Exception as e:
        return [f"サジェストの取得に失敗しました: {e}"]
