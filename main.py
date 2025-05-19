#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import requests
import urllib.parse
import time
import datetime
import random
import os
import subprocess

from fastapi import FastAPI, Response, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response as FastAPIResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pytube import YouTube, Search, Channel, Playlist

# ------------------------------------------------------
# ユーザーエージェントの設定（必要に応じて各種エージェントを追加）
user_agents = [
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/94.0.4606.61 Safari/537.36',
  # 他の User-Agent もここに追加…
]

def getRandomUserAgent():
    return {'User-Agent': random.choice(user_agents)}

# ------------------------------------------------------
# FastAPI の設定
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/js", StaticFiles(directory="./statics/js"), name="static")
app.mount("/css", StaticFiles(directory="./statics/css"), name="static")
app.mount("/img", StaticFiles(directory="./statics/img"), name="static")
app.add_middleware(GZipMiddleware, minimum_size=1000)

templates = Jinja2Templates(directory="templates")

# ------------------------------------------------------
# Cookie チェック
def checkCookie(cookie):
    return cookie == "True"

# ------------------------------------------------------
# ホームエンドポイント
@app.get("/", response_class=HTMLResponse)
def home(response: Response, request: Request, yuki: str = Cookie(default="False")):
    if checkCookie(yuki):
        response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
        return templates.TemplateResponse("home.html", {"request": request})
    # ログイン状態でない場合のリダイレクト例（任意の URL に変更可）
    return RedirectResponse("/genesis")

# ------------------------------------------------------
# 動画データ取得（PyTube の YouTube クラスを利用）
@app.get("/watch", response_class=HTMLResponse)
def watch(v: str, response: Response, request: Request, yuki: str = Cookie(default="False"), proxy: str = Cookie(default="")):
    if not checkCookie(yuki):
        return RedirectResponse("/")
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    try:
        video_url = f"https://www.youtube.com/watch?v={v}"
        yt = YouTube(video_url, headers=getRandomUserAgent())
    except Exception as e:
        return HTMLResponse(content=f"動画の取得に失敗しました: {e}", status_code=500)
    
    # progressive フォーマットで動画ストリーム URL を抽出
    video_urls = [stream.url for stream in yt.streams.filter(progressive=True)]
    video_data = {
         "title": yt.title,
         "description_html": yt.description.replace("\n", "<br>"),
         "author": yt.author,
         "video_urls": video_urls,
         "length_text": str(datetime.timedelta(seconds=yt.length)),
         "views": yt.views,
    }

    # Cookie やその他条件でテンプレートを切り替える例（ume_toggle などの Cookie をチェック）
    template_name = "ume.html" if request.cookies.get("ume_toggle", "false") == "true" else "video.html"
    
    return templates.TemplateResponse(template_name, {
          "request": request,
          "videoid": v,
          "videourls": video_data["video_urls"],
          "description": video_data["description_html"],
          "video_title": video_data["title"],
          "author": video_data["author"],
          "length_text": video_data["length_text"],
          "view_count": video_data["views"],
          "proxy": proxy
    })

# ------------------------------------------------------
# 検索機能（PyTube の Search クラスを利用）
@app.get("/search", response_class=HTMLResponse)
def search(q: str, response: Response, request: Request, page: int = 1, yuki: str = Cookie(default="False"), proxy: str = Cookie(default="")):
    if not checkCookie(yuki):
        return RedirectResponse("/")
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    # pytube の Search はシンプルな検索結果（ページネーションは柔軟ではないため、ここでは全結果を返す）
    s = Search(q)
    results = []
    for yt_obj in s.results:
         results.append({
            "type": "video",
            "title": yt_obj.title,
            "id": yt_obj.video_id,
            "author": yt_obj.author,
            "length": str(datetime.timedelta(seconds=yt_obj.length)) if yt_obj.length else "N/A",
            "views": yt_obj.views
         })
    next_page = f"/search?q={urllib.parse.quote(q)}&page={page + 1}"
    return templates.TemplateResponse("search.html", {
           "request": request,
           "results": results,
           "word": q,
           "next": next_page,
           "proxy": proxy
    })

# ------------------------------------------------------
# チャンネル情報取得（PyTube の Channel クラスを利用）
@app.get("/channel/{channelid}", response_class=HTMLResponse)
def channel(channelid: str, response: Response, request: Request, yuki: str = Cookie(default="False"), proxy: str = Cookie(default="")):
    if not checkCookie(yuki):
        return RedirectResponse("/")
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    try:
        channel_url = f"https://www.youtube.com/channel/{channelid}"
        ch = Channel(channel_url)
    except Exception as e:
        return HTMLResponse(content=f"チャンネルの取得に失敗しました: {e}", status_code=500)
    
    videos = []
    # チャンネル内の上位動画（例: 最初の 5 件）を取得
    for v_url in ch.video_urls[:5]:
         try:
             yt = YouTube(v_url)
             videos.append({
                 "type": "video",
                 "title": yt.title,
                 "id": yt.video_id,
                 "published": "",  # pytube では公開日が取得できない場合が多い
                 "views": yt.views,
                 "length_str": str(datetime.timedelta(seconds=yt.length))
             })
         except Exception:
             continue

    channel_info = {
         "channel_name": ch.channel_name,
         "channel_icon": ch.thumbnail_url,
         "channel_profile": "",       # 詳細なプロフィールは pytube では取得不可
         "subscribers_count": ""      # 購読者数は取得できません
    }
    
    return templates.TemplateResponse("channel.html", {
         "request": request,
         "results": videos,
         "channel_name": channel_info["channel_name"],
         "channel_icon": channel_info["channel_icon"],
         "channel_profile": channel_info["channel_profile"],
         "cover_img_url": "",          # カバー画像の情報があればここに追加
         "subscribers_count": channel_info["subscribers_count"],
         "proxy": proxy
    })

# ------------------------------------------------------
# プレイリスト取得（PyTube の Playlist クラスを利用）
@app.get("/playlist", response_class=HTMLResponse)
def playlist(list: str, page: int = 1, response: Response, request: Request, yuki: str = Cookie(default="False"), proxy: str = Cookie(default="")):
    if not checkCookie(yuki):
        return RedirectResponse("/")
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    playlist_url = f"https://www.youtube.com/playlist?list={list}"
    try:
        pl = Playlist(playlist_url)
    except Exception as e:
        return HTMLResponse(content=f"プレイリストの取得に失敗しました: {e}", status_code=500)
    
    videos = []
    for v_url in pl.video_urls:
         try:
             yt = YouTube(v_url)
             videos.append({
                 "title": yt.title,
                 "id": yt.video_id,
                 "author": yt.author,
                 "type": "video"
             })
         except Exception:
             continue
    
    return templates.TemplateResponse("search.html", {
         "request": request,
         "results": videos,
         "word": "",
         "next": f"/playlist?list={list}",
         "proxy": proxy
    })

# ------------------------------------------------------
# コメント取得（pytube では対応していないため、サンプルとして固定メッセージを返す）
@app.get("/comments", response_class=HTMLResponse)
def comments(request: Request, v: str):
    return templates.TemplateResponse("comments.html", {
         "request": request,
         "comments": [{
             "author": "N/A",
             "authoricon": "",
             "authorid": "",
             "body": "pytube ではコメント取得はサポートされていません。"
         }]
    })

# ------------------------------------------------------
# サムネイル取得エンドポイント（YouTube のサムネイル画像 URL）
@app.get("/thumbnail")
def thumbnail(v: str):
    thumbnail_url = f"https://img.youtube.com/vi/{v}/0.jpg"
    try:
        resp = requests.get(thumbnail_url)
        return FastAPIResponse(content=resp.content, media_type="image/jpeg")
    except Exception as e:
        return FastAPIResponse(content=f"サムネイルの取得に失敗しました: {e}", status_code=500)

# ------------------------------------------------------
# サジェスト（autocomplete）エンドポイント
@app.get("/suggest")
def suggest(keyword: str):
    try:
        resp = requests.get(
            "http://www.google.com/complete/search?client=youtube&hl=ja&ds=yt&q=" + urllib.parse.quote(keyword),
            headers=getRandomUserAgent()
        )
        # google の返答のうち、必要な部分のみを JSON 部分として抽出
        suggestions = [i[0] for i in json.loads(resp.text[19:-1])[1]]
        return suggestions
    except Exception as e:
        return [f"サジェストの取得に失敗しました: {e}"]
