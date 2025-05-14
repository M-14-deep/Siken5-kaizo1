import json
import requests
import urllib.parse
import time
import datetime
import random
import os
import subprocess
from cache import cache
import ast
# タイムアウト設定
max_api_wait_time = (1.5, 1)
max_time = 10


user_agents = [
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3864.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.13; rv:62.0) Gecko/20100101 Firefox/62.0',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.13; rv:67.0) Gecko/20100101 Firefox/67.0',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.13; rv:68.0) Gecko/20100101 Firefox/68.0',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:61.0) Gecko/20100101 Firefox/61.0',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:62.0) Gecko/20100101 Firefox/62.0',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:92.0) Gecko/20100101 Firefox/92.0',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36 Edge/17.17134',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36 Edg/94.0.992.31',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.0 Safari/605.1.15',
  'Mozilla/5.0 (iPhone; CPU iPhone OS 12_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.0 Mobile/15E148 Safari/604.1'
]

def getRandomUserAgent():
    user_agent = random.choice(user_agents)
    print(user_agent)
    return {'User-Agent': user_agent}

# ----------------- InvidiousAPI クラスの拡張 -----------------
class InvidiousAPI:
    def __init__(self):
        # GitHub上の API 情報ファイルを取得（Python の辞書形式の文字列と仮定）
        self.all = ast.literal_eval(requests.get(
            'https://github.com/M-14-deep/Kari/raw/refs/heads/main/kari',
            headers=getRandomUserAgent(),
            timeout=(1.0, 0.5)
        ).text)
        
        self.video       = self.all['video']
        self.playlist    = self.all['playlist']
        self.search      = self.all['search']
        self.channel     = self.all['channel']
        self.comments    = self.all['comments']
        self.check_video = False

        # piped キーがあれば個別に保持する
        if "piped" in self.all:
            self.piped_video    = self.all["piped"]
            self.piped_comments = self.all["piped"]
        else:
            self.piped_video    = []
            self.piped_comments = []

        # デフォルト「auto」は両方を統合したリストとする
        self.multiple_video_apis    = self.video.copy()
        self.multiple_video_apis.extend(self.piped_video)
        self.multiple_comments_apis = self.comments.copy()
        self.multiple_comments_apis.extend(self.piped_comments)

    def info(self):
        return {
            'API': self.all,
            'checkVideo': self.check_video
        }

invidious_api = InvidiousAPI()

# ----------------- 補助関数 -----------------
class APITimeoutError(Exception):
    pass

def isJSON(json_str):
    try:
        json.loads(json_str)
        return True
    except json.JSONDecodeError:
        return False

def updateList(list_obj, str_val):
    list_obj.append(str_val)
    list_obj.remove(str_val)
    return list_obj

def requestAPI(path, api_urls):
    starttime = time.time()
    for api in api_urls:
        if time.time() - starttime >= max_time - 1:
            break
        try:
            full_url = api + 'api/v1' + path
            print(full_url)
            res = requests.get(full_url, headers=getRandomUserAgent(), timeout=max_api_wait_time)
            if res.status_code == requests.codes.ok and isJSON(res.text):
                if invidious_api.check_video and path.startswith('/video/'):
                    video_res = requests.get(
                        json.loads(res.text)['formatStreams'][0]['url'],
                        headers=getRandomUserAgent(),
                        timeout=(3.0, 0.5)
                    )
                    if 'video' not in video_res.headers.get('Content-Type', ''):
                        print(f"No Video(True): {api} ({video_res.headers.get('Content-Type','')})")
                        updateList(api_urls, api)
                        continue
                if path.startswith('/channel/') and json.loads(res.text).get("latestvideo", []) == []:
                    print(f"No Channel: {api}")
                    updateList(api_urls, api)
                    continue
                print(f"Success: {path.split('/')[1]} from {api}")
                return res.text
            elif isJSON(res.text):
                print(f"Returned Err0r(JSON) from {api}: {json.loads(res.text)['error'].replace('error', 'err0r')}")
                updateList(api_urls, api)
            else:
                print(f"Returned Err0r from {api}: {res.text[:100]}")
                updateList(api_urls, api)
        except Exception as e:
            print(f"Err0r: {api} - {e}")
            updateList(api_urls, api)
    raise APITimeoutError("APIがタイムアウトしました")

# ----------------- 複数の動画情報取得関数（UI選択対応） -----------------
def getMultipleVideoData(videoid, endpoint_type="auto"):
    """
    endpoint_type = "invidious" / "piped" / "auto"
    """
    if endpoint_type == "invidious":
        endpoints = invidious_api.video
    elif endpoint_type == "piped":
        endpoints = invidious_api.piped_video
    else:
        endpoints = invidious_api.multiple_video_apis

    def extract_video_data(api, t):
        # 推奨動画の抽出（キー名が異なる場合に対応）
        if 'recommendedvideo' in t:
            recommended_videos = t["recommendedvideo"]
        elif 'recommendedVideos' in t:
            recommended_videos = t["recommendedVideos"]
        else:
            recommended_videos = [{
                "videoId": "Load Failed",
                "title": "Load Failed",
                "authorId": "Load Failed",
                "author": "Load Failed",
                "lengthSeconds": 0,
                "viewCountText": "Load Failed"
            }]
        adaptiveFormats = t.get("adaptiveFormats", [])
        highstream_url, audio_url = None, None
        for stream in adaptiveFormats:
            if stream.get("container") == "webm" and stream.get("resolution") == "1080p":
                highstream_url = stream.get("url")
                break
        if not highstream_url:
            for stream in adaptiveFormats:
                if stream.get("container") == "webm" and stream.get("resolution") == "720p":
                    highstream_url = stream.get("url")
                    break
        for stream in adaptiveFormats:
            if stream.get("container") == "m4a" and stream.get("audioQuality") == "AUDIO_QUALITY_MEDIUM":
                audio_url = stream.get("url")
                break

        streamUrls = [
            {'url': stream['url'], 'resolution': stream['resolution']}
            for stream in adaptiveFormats if stream.get('container') == 'webm' and stream.get('resolution')
        ]
        return {
            "api": api,
            "video_urls": list(reversed([i.get("url", "") for i in t.get("formatStreams", [])]))[:2],
            "highstream_url": highstream_url,
            "audio_url": audio_url,
            "description_html": t.get("descriptionHtml", "").replace("\n", "<br>"),
            "title": t.get("title", ""),
            "length_text": str(datetime.timedelta(seconds=t.get("lengthSeconds", 0))),
            "author_id": t.get("authorId", ""),
            "author": t.get("author", ""),
            "author_thumbnails_url": t.get("authorThumbnails", [{"url": ""}])[-1].get("url", ""),
            "view_count": t.get("viewCount", ""),
            "like_count": t.get("likeCount", ""),
            "subscribers_count": t.get("subCountText", ""),
            "streamUrls": streamUrls,
            "recommended_videos": [
                {
                    "video_id": i.get("videoId", "Load Failed"),
                    "title": i.get("title", "Load Failed"),
                    "author_id": i.get("authorId", "Load Failed"),
                    "author": i.get("author", "Load Failed"),
                    "length_text": str(datetime.timedelta(seconds=i.get("lengthSeconds", 0))),
                    "view_count_text": i.get("viewCountText", "Load Failed")
                } for i in recommended_videos
            ]
        }

    collected_data = []
    for api in endpoints:
        full_url = api + 'api/v1' + f"/videos/{urllib.parse.quote(videoid)}"
        print(f"Trying video API: {full_url}")
        try:
            res = requests.get(full_url, headers=getRandomUserAgent(), timeout=max_api_wait_time)
            if res.status_code == requests.codes.ok and isJSON(res.text):
                t = json.loads(res.text)
                data = extract_video_data(api, t)
                collected_data.append(data)
        except Exception as e:
            print(f"Error with video API {api}: {e}")
            continue
    if not collected_data:
        raise APITimeoutError("動画取得APIがタイムアウトしました")
    return collected_data

# ----------------- 複数のコメント取得関数（UI選択対応） -----------------
def getMultipleCommentsData(videoid, endpoint_type="auto"):
    if endpoint_type == "invidious":
        endpoints = invidious_api.comments
    elif endpoint_type == "piped":
        endpoints = invidious_api.piped_comments
    else:
        endpoints = invidious_api.multiple_comments_apis

    collected_comments = []
    for api in endpoints:
        full_url = api + 'api/v1' + f"/comments/{urllib.parse.quote(videoid)}?hl=jp"
        print(f"Trying comments API: {full_url}")
        try:
            res = requests.get(full_url, headers=getRandomUserAgent(), timeout=max_api_wait_time)
            if res.status_code == requests.codes.ok and isJSON(res.text):
                data = json.loads(res.text)
                comments = data.get("comments", [])
                formatted_comments = [
                    {
                        "author": com.get("author", ""),
                        "authoricon": com.get("authorThumbnails", [{"url": ""}])[-1].get("url", ""),
                        "authorid": com.get("authorId", ""),
                        "body": com.get("contentHtml", "").replace("\n", "<br>")
                    } for com in comments
                ]
                collected_comments.append({
                    "api": api,
                    "comments": formatted_comments
                })
        except Exception as e:
            print(f"Error with comments API {api}: {e}")
            continue
    if not collected_comments:
        raise APITimeoutError("コメント取得APIがタイムアウトしました")
    return collected_comments

def getInfo(request):
    return json.dumps([version, os.environ.get('RENDER_EXTERNAL_URL'), str(request.scope["headers"]), str(request.scope['router'])[39:-2]])

failed = "Load Failed"

def getVideoData(videoid):
    t = json.loads(requestAPI(f"/videos/{urllib.parse.quote(videoid)}", invidious_api.video))

    # 推奨動画の情報（キー名の違いに対応）
    if 'recommendedvideo' in t:
        recommended_videos = t["recommendedvideo"]
    elif 'recommendedVideos' in t:
        recommended_videos = t["recommendedVideos"]
    else:
        recommended_videos = [{
            "videoId": failed,
            "title": failed,
            "authorId": failed,
            "author": failed,
            "lengthSeconds": 0,
            "viewCountText": "Load Failed"
        }]

    # 【新規追加】adaptiveFormats から高画質動画と音声の URL を抽出する
    adaptiveFormats = t.get("adaptiveFormats", [])
    highstream_url = None
    audio_url = None

    # 高画質: container == 'webm' かつ resolution == '1080p' のストリーム
    for stream in adaptiveFormats:
        if stream.get("container") == "webm" and stream.get("resolution") == "1080p":
            highstream_url = stream.get("url")
            break
    if not highstream_url:
        for stream in adaptiveFormats:
            if stream.get("container") == "webm" and stream.get("resolution") == "720p":
                highstream_url = stream.get("url")
                break


    # 音声: container == 'm4a' かつ audioQuality == 'AUDIO_QUALITY_MEDIUM' のストリーム
    for stream in adaptiveFormats:
        if stream.get("container") == "m4a" and stream.get("audioQuality") == "AUDIO_QUALITY_MEDIUM":
            audio_url = stream.get("url")
            break

    adaptive = t.get('adaptiveFormats', [])
    streamUrls = [
        {
            'url': stream['url'],
            'resolution': stream['resolution']
        }
        for stream in adaptive
        if stream.get('container') == 'webm' and stream.get('resolution')
    ]
    return [
      {
        # 既存処理（ここでは formatStreams のURLを逆順にして上位2件を使用）
        'video_urls': list(reversed([i["url"] for i in t["formatStreams"]]))[:2],
        # 追加：高画質動画と音声のURL
        'highstream_url': highstream_url,
        'audio_url': audio_url,
        'description_html': t["descriptionHtml"].replace("\n", "<br>"),
        'title': t["title"],
        'length_text': str(datetime.timedelta(seconds=t["lengthSeconds"])),
        'author_id': t["authorId"],
        'author': t["author"],
        'author_thumbnails_url': t["authorThumbnails"][-1]["url"],
        'view_count': t["viewCount"],
        'like_count': t["likeCount"],
        'subscribers_count': t["subCountText"],
        'streamUrls': streamUrls
    },

    [
      {
        "video_id": i["videoId"],
        "title": i["title"],
        "author_id": i["authorId"],
        "author": i["author"],
        "length_text": str(datetime.timedelta(seconds=i["lengthSeconds"])),
        "view_count_text": i["viewCountText"]
    } for i in recommended_videos]
    
]

def getSearchData(q, page):

    def formatSearchData(data_dict):
        if data_dict["type"] == "video":
            return {
                "type": "video",
                "title": data_dict["title"] if 'title' in data_dict else failed,
                "id": data_dict["videoId"] if 'videoId' in data_dict else failed,
                "authorId": data_dict["authorId"] if 'authorId' in data_dict else failed,
                "author": data_dict["author"] if 'author' in data_dict else failed,
                "published": data_dict["publishedText"] if 'publishedText' in data_dict else failed,
                "length": str(datetime.timedelta(seconds=data_dict["lengthSeconds"])),
                "view_count_text": data_dict["viewCountText"]
            }
            
        elif data_dict["type"] == "playlist":
            return {
                    "type": "playlist",
                    "title": data_dict["title"] if 'title' in data_dict else failed,
                    "id": data_dict['playlistId'] if 'playlistId' in data_dict else failed,
                    "thumbnail": data_dict["playlistThumbnail"] if 'playlistThumbnail' in data_dict else failed,
                    "count": data_dict["videoCount"] if 'videoCount' in data_dict else failed
                }
            
        elif data_dict["authorThumbnails"][-1]["url"].startswith("https"):
            return {
                "type": "channel",
                "author": data_dict["author"] if 'author' in data_dict else failed,
                "id": data_dict["authorId"] if 'authorId' in data_dict else failed,
                "thumbnail": data_dict["authorThumbnails"][-1]["url"] if 'authorThumbnails' in data_dict and len(data_dict["authorThumbnails"]) and 'url' in data_dict["authorThumbnails"][-1] else failed
            }
        else:
            return {
                "type": "channel",
                "author": data_dict["author"] if 'author' in data_dict else failed,
                "id": data_dict["authorId"] if 'authorId' in data_dict else failed,
                "thumbnail": "https://" + data_dict['authorThumbnails'][-1]['url']
            }

    # "datas"というのは気持ち悪いかもしれないが、複数のデータが入っていると明示できるという
    # メリットの方がコードを書く上では大きい
    datas_dict = json.loads(requestAPI(f"/search?q={urllib.parse.quote(q)}&page={page}&hl=jp", invidious_api.search))
    return [formatSearchData(data_dict) for data_dict in datas_dict]


def getChannelData(channelid):
    t = json.loads(requestAPI(f"/channels/{urllib.parse.quote(channelid)}", invidious_api.channel))
    if 'latestvideo' in t:
        latest_videos = t['latestvideo']
    elif 'latestVideos' in t:
        latest_videos = t['latestVideos']
    else:
        latest_videos = {
            "title": failed,
            "videoId": failed,
            "authorId": failed,
            "author": failed,
            "publishedText": failed,
            "viewCountText": "0",
            "lengthSeconds": "0"
        }
    
    
    return [
        [
            {
                # 直近の動画
                "type":"video",
                "title": i["title"],
                "id": i["videoId"],
                "authorId": t["authorId"],
                "author": t["author"],
                "published": i["publishedText"],
                "view_count_text": i['viewCountText'],
                "length_str": str(datetime.timedelta(seconds=i["lengthSeconds"]))
            } for i in latest_videos
        ], {
            # チャンネル情報
            "channel_name": t["author"],
            "channel_icon": t["authorThumbnails"][-1]["url"],
            "channel_profile": t["descriptionHtml"],
            "author_banner": urllib.parse.quote(t["authorBanners"][0]["url"], safe="-_.~/:") if 'authorBanners' in t and len(t['authorBanners']) else '',
            "subscribers_count": t["subCount"],
            "tags": t["tags"]
        }
    ]

def getPlaylistData(listid, page):
    t = json.loads(requestAPI(f"/playlists/{urllib.parse.quote(listid)}?page={urllib.parse.quote(page)}", invidious_api.playlist))["videos"]
    return [{"title": i["title"], "id": i["videoId"], "authorId": i["authorId"], "author": i["author"], "type": "video"} for i in t]

def getCommentsData(videoid):
    t = json.loads(requestAPI(f"/comments/{urllib.parse.quote(videoid)}?hl=jp", invidious_api.comments))["comments"]
    return [{"author": i["author"], "authoricon": i["authorThumbnails"][-1]["url"], "authorid": i["authorId"], "body": i["contentHtml"].replace("\n", "<br>")} for i in t]

'''
使われていないし戻り値も設定されていないためコメントアウト
def get_replies(videoid, key):
    t = json.loads(requestAPI(f"/comments/{videoid}?hmac_key={key}&hl=jp&format=html", invidious_api.comments))["contentHtml"]
'''


def checkCookie(cookie):
    isTrue = True if cookie == "True" else False
    return isTrue

def getVerifyCode():
    try:
        result = subprocess.run(["./yukiverify"], encoding='utf-8', stdout=subprocess.PIPE)
        hashed_password = result.stdout.strip()
        return hashed_password
    except subprocess.CalledProcessError as e:
        print(f"getVerifyCode__Error: {e}")
        return None

# ----------------- FastAPI アプリケーションとエンドポイント -----------------
from fastapi import FastAPI, Response, Cookie, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Union

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/js", StaticFiles(directory="./statics/js"), name="static")
app.mount("/css", StaticFiles(directory="./statics/css"), name="static")
app.mount("/img", StaticFiles(directory="./statics/img"), name="static")
app.mount("/genesis", StaticFiles(directory="./blog", html=True), name="static")
app.add_middleware(GZipMiddleware, minimum_size=1000)
template = Jinja2Templates(directory='templates').TemplateResponse

def checkCookie(cookie: Union[str, None]):
    return cookie == "True"

# ----------------- トップページ -----------------
@app.get("/", response_class=HTMLResponse)
def home(response: Response, request: Request, yuki: Union[str, None] = Cookie(None)):
    if checkCookie(yuki):
        response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
        return template("home.html", {"request": request})
    return RedirectResponse(url="/genesis")

# ----------------- 設定画面：API種別切替 UI -----------------
@app.get("/settings", response_class=HTMLResponse)
def settings_get(request: Request, endpoint: Union[str, None] = Cookie(None)):
    # クッキーに保存されているAPI種別（"auto", "invidious", "piped"）を読み込み
    current = endpoint if endpoint in ["auto", "invidious", "piped"] else "auto"
    return template("settings.html", {"request": request, "current": current})

@app.post("/settings", response_class=RedirectResponse)
def settings_post(response: Response, endpoint: str = Form(...)):
    # ユーザーの選択値を Cookie に保存（例：7日間有効）
    if endpoint not in ["auto", "invidious", "piped"]:
        endpoint = "auto"
    response.set_cookie(key="endpoint", value=endpoint, max_age=60 * 60 * 24 * 7)
    return RedirectResponse(url="/", status_code=302)

# ----------------- 動画視聴エンドポイント -----------------
@app.get('/watch', response_class=HTMLResponse)
def video(v: str, response: Response, request: Request, 
          yuki: Union[str, None] = Cookie(None), 
          proxy: Union[str, None] = Cookie(None),
          endpoint: Union[str, None] = Cookie(None)):
    if not checkCookie(yuki):
        return RedirectResponse(url="/")
    response.set_cookie("yuki", "True", max_age=7 * 24 * 60 * 60)
    # Cookie "endpoint" により使用するAPIを切替（無ければ "auto"）
    ep_type = endpoint if endpoint in ["auto", "invidious", "piped"] else "auto"
    video_data_list = getMultipleVideoData(v, ep_type)
    return [
        {
            'video_urls': list(reversed([i["url"] for i in t["formatStreams"]]))[:2],
            'description_html': t["descriptionHtml"].replace("\n", "<br>"),
            'title': t["title"],
            'length_text': str(datetime.timedelta(seconds=t["lengthSeconds"])),
            'author_id': t["authorId"],
            'author': t["author"],
            'author_thumbnails_url': t["authorThumbnails"][-1]["url"],
            'view_count': t["viewCount"],
            'like_count': t["likeCount"],
            'subscribers_count': t["subCountText"]
        },
        [
            {
                "video_id": i["videoId"],
                "title": i["title"],
                "author_id": i["authorId"],
                "author": i["author"],
                "length_text": str(datetime.timedelta(seconds=i["lengthSeconds"])),
                "view_count_text": i["viewCountText"]
            } for i in recommended_videos
    ]
    ]
    '''
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    return template('video.html', {
        "request": request,
        "videoid": v,
        "videourls": video_data[0]['video_urls'],
        "description": video_data[0]['description_html'],
        "video_title": video_data[0]['title'],
        "author_id": video_data[0]['author_id'],
        "author_icon": video_data[0]['author_thumbnails_url'],
        "author": video_data[0]['author'],
        "length_text": video_data[0]['length_text'],
        "view_count": video_data[0]['view_count'],
        "like_count": video_data[0]['like_count'],
        "subscribers_count": video_data[0]['subscribers_count'],
        "recommended_videos": video_data[1],
        "proxy":proxy
    })
# ----------------- 動画情報＋コメント一括取得エンドポイント -----------------
@app.get("/complete", response_class=JSONResponse)
def complete(v: str, response: Response, request: Request, endpoint: Union[str, None] = Cookie(None)):
    ep_type = endpoint if endpoint in ["auto", "invidious", "piped"] else "auto"
    video_data_results  = getMultipleVideoData(v, ep_type)
    comments_data_results = getMultipleCommentsData(v, ep_type)
    return {"video_data": video_data_results, "comments_data": comments_data_results}

# 既存の getSearchData, getChannelData, getPlaylistData, getCommentsData, getVerifyCode などは省略
def getVerifyCode():
    try:
        result = subprocess.run(["./yukiverify"], encoding='utf-8', stdout=subprocess.PIPE)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"getVerifyCode__Error: {e}")
        return None

@app.get('/w', response_class=HTMLResponse)
def video(v:str, response: Response, request: Request, yuki: Union[str] = Cookie(None), proxy: Union[str] = Cookie(None)):
    # v: video_id
    if not(checkCookie(yuki)):
        return redirect("/")
    response.set_cookie(key="yuki", value="True", max_age=7*24*60*60)
    video_data = getVideoData(v)
    '''
    return [
        {
            'video_urls': list(reversed([i["url"] for i in t["formatStreams"]]))[:2],
            'highstream_url': highstream_url,
            'audio_url': audio_url,
            'description_html': t["descriptionHtml"].replace("\n", "<br>"),
            'title': t["title"],
            'length_text': str(datetime.timedelta(seconds=t["lengthSeconds"])),
            'author_id': t["authorId"],
            'author': t["author"],
            'author_thumbnails_url': t["authorThumbnails"][-1]["url"],
            'view_count': t["viewCount"],
            'like_count': t["likeCount"],
            'subscribers_count': t["subCountText"]
        },
        [
            {
                "video_id": i["videoId"],
                "title": i["title"],
                "author_id": i["authorId"],
                "author": i["author"],
                "length_text": str(datetime.timedelta(seconds=i["lengthSeconds"])),
                "view_count_text": i["viewCountText"]
            } for i in recommended_videos
        ]
    ]
    '''
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    return template('hiquo.html', {
        "request": request,
        "videoid": v,
        "videourls": video_data[0]['video_urls'],
        "highstream_url": video_data[0]['highstream_url'],
        "audio_url": video_data[0]['audio_url'],
        "description": video_data[0]['description_html'],
        "video_title": video_data[0]['title'],
        "author_id": video_data[0]['author_id'],
        "author_icon": video_data[0]['author_thumbnails_url'],
        "author": video_data[0]['author'],
        "length_text": video_data[0]['length_text'],
        "view_count": video_data[0]['view_count'],
        "like_count": video_data[0]['like_count'],
        "subscribers_count": video_data[0]['subscribers_count'],
        "recommended_videos": video_data[1],
        "proxy":proxy
    })
@app.get('/ume', response_class=HTMLResponse)
def video(v:str, response: Response, request: Request, yuki: Union[str] = Cookie(None), proxy: Union[str] = Cookie(None)):
    # v: video_id
    if not(checkCookie(yuki)):
        return redirect("/")
    response.set_cookie(key="yuki", value="True", max_age=7*24*60*60)
    video_data = getVideoData(v)
    '''
    return [
        {
            'video_urls': list(reversed([i["url"] for i in t["formatStreams"]]))[:2],
            'description_html': t["descriptionHtml"].replace("\n", "<br>"),
            'title': t["title"],
            'length_text': str(datetime.timedelta(seconds=t["lengthSeconds"])),
            'author_id': t["authorId"],
            'author': t["author"],
            'author_thumbnails_url': t["authorThumbnails"][-1]["url"],
            'view_count': t["viewCount"],
            'like_count': t["likeCount"],
            'subscribers_count': t["subCountText"]
        },
        [
            {
                "title": i["title"],
                "author_id": i["authorId"],
                "author": i["author"],
                "length_text": str(datetime.timedelta(seconds=i["lengthSeconds"])),
                "view_count_text": i["viewCountText"]
            } for i in recommended_videos
        ]
    ]
    '''
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    return template('ume.html', {
        "request": request,
        "videoid": v,
        "videourls": video_data[0]['video_urls'],
        "description": video_data[0]['description_html'],
        "video_title": video_data[0]['title'],
        "author_id": video_data[0]['author_id'],
        "author_icon": video_data[0]['author_thumbnails_url'],
        "author": video_data[0]['author'],
        "length_text": video_data[0]['length_text'],
        "view_count": video_data[0]['view_count'],
        "like_count": video_data[0]['like_count'],
        "subscribers_count": video_data[0]['subscribers_count'],
        "recommended_videos": video_data[1],
        "proxy":proxy
    })

@app.get('/ww', response_class=HTMLResponse)
def video(v:str, response: Response, request: Request, yuki: Union[str] = Cookie(None), proxy: Union[str] = Cookie(None)):
    # v: video_id
    if not(checkCookie(yuki)):
        return redirect("/")
    response.set_cookie(key="yuki", value="True", max_age=7*24*60*60)
    video_data = getVideoData(v)
    '''
    return [
        {
            'video_urls': list(reversed([i["url"] for i in t["formatStreams"]]))[:2],
            'description_html': t["descriptionHtml"].replace("\n", "<br>"),
            'title': t["title"],
            'length_text': str(datetime.timedelta(seconds=t["lengthSeconds"])),
            'author_id': t["authorId"],
            'author': t["author"],
            'author_thumbnails_url': t["authorThumbnails"][-1]["url"],
            'view_count': t["viewCount"],
            'like_count': t["likeCount"],
            'subscribers_count': t["subCountText"],
            'streamUrls': streamUrls
        },
        [
            {
                "video_id": i["videoId"],
                "title": i["title"],
                "author_id": i["authorId"],
                "author": i["author"],
                "length_text": str(datetime.timedelta(seconds=i["lengthSeconds"])),
                "view_count_text": i["viewCountText"]
            } for i in recommended_videos
        ]
    ]
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    return template('watch.html', { # watch.htmlを準備してください( ・∇・)。通常の再生 + 画質を選択できる機能があると良い。
        "request": request,         # 画質のデータはstreamUrls.resolutionに入っています。ストリームURLはstreamUrls.url。
        "videoid": v,
        "videourls": video_data[0]['video_urls'],
        "description": video_data[0]['description_html'],
        "video_title": video_data[0]['title'],
        "author_id": video_data[0]['author_id'],
        "author_icon": video_data[0]['author_thumbnails_url'],
        "author": video_data[0]['author'],
        "length_text": video_data[0]['length_text'],
        "view_count": video_data[0]['view_count'],
        "like_count": video_data[0]['like_count'],
        "subscribers_count": video_data[0]['subscribers_count'],
        "streamUrls": video_data[0]['streamUrls'], #ここに高画質ストリーム(対応する画質を含む)を収納
        "recommended_videos": video_data[1],
        "proxy":proxy
    })



@app.get("/search", response_class=HTMLResponse)
def search(q:str, response: Response, request: Request, page:Union[int, None]=1, yuki: Union[str] = Cookie(None), proxy: Union[str] = Cookie(None)):
    if not(checkCookie(yuki)):
        return redirect("/")
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    return template("search.html", {"request": request, "results":getSearchData(q, page), "word":q, "next":f"/search?q={q}&page={page + 1}", "proxy":proxy})

@app.get("/hashtag/{tag}")
def search(tag:str, response: Response, request: Request, page:Union[int, None]=1, yuki: Union[str] = Cookie(None)):
    if not(checkCookie(yuki)):
        return redirect("/")
    return redirect(f"/search?q={tag}")

@app.get("/channel/{channelid}", response_class=HTMLResponse)
def channel(channelid:str, response: Response, request: Request, yuki: Union[str] = Cookie(None), proxy: Union[str] = Cookie(None)):
    if not(checkCookie(yuki)):
        return redirect("/")
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    t = getChannelData(channelid)
    return template("channel.html", {"request": request, "results": t[0], "channel_name": t[1]["channel_name"], "channel_icon": t[1]["channel_icon"], "channel_profile": t[1]["channel_profile"], "cover_img_url": t[1]["author_banner"], "subscribers_count": t[1]["subscribers_count"], "proxy": proxy})

@app.get("/playlist", response_class=HTMLResponse)
def playlist(list:str, response: Response, request: Request, page:Union[int, None]=1, yuki: Union[str] = Cookie(None), proxy: Union[str] = Cookie(None)):
    if not(checkCookie(yuki)):
        return redirect("/")
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    return template("search.html", {"request": request, "results": getPlaylistData(list, str(page)), "word": "", "next": f"/playlist?list={list}", "proxy": proxy})

@app.get("/comments")
def comments(request: Request, v:str):
    return template("comments.html", {"request": request, "comments": getCommentsData(v)})

@app.get("/thumbnail")
def thumbnail(v:str):
    return Response(content = requests.get(f"https://img.youtube.com/vi/{v}/0.jpg").content, media_type=r"image/jpeg")

@app.get("/suggest")
def suggest(keyword:str):
    return [i[0] for i in json.loads(requests.get("http://www.google.com/complete/search?client=youtube&hl=ja&ds=yt&q=" + urllib.parse.quote(keyword), headers=getRandomUserAgent()).text[19:-1])[1]]





@cache(seconds=120)
def getSource(name):
    return requests.get(f'https://raw.githubusercontent.com/LunaKamituki/yuki-source/refs/heads/main/{name}.html', headers=getRandomUserAgent()).text

@app.get("/bbs", response_class=HTMLResponse)
def bbs(request: Request, name: Union[str, None] = "", seed:Union[str, None]="", channel:Union[str, None]="main", verify:Union[str, None]="false", yuki: Union[str] = Cookie(None)):
    if not(checkCookie(yuki)):
        return redirect("/")
    res = HTMLResponse(no_robot_meta_tag + requests.get(f"{url}bbs?name={urllib.parse.quote(name)}&seed={urllib.parse.quote(seed)}&channel={urllib.parse.quote(channel)}&verify={urllib.parse.quote(verify)}", cookies={"yuki":"True"}).text.replace('AutoLink(xhr.responseText);', 'urlConvertToLink(xhr.responseText);') + getSource('bbs'))
    return res

@cache(seconds=5)
def getCachedBBSAPI(verify, channel):
    return requests.get(f"{url}bbs/api?t={urllib.parse.quote(str(int(time.time()*1000)))}&verify={urllib.parse.quote(verify)}&channel={urllib.parse.quote(channel)}", cookies={"yuki":"True"}).text

@app.get("/bbs/api", response_class=HTMLResponse)
def bbsAPI(request: Request, t: str, channel:Union[str, None]="main", verify: Union[str, None] = "false"):
    return getCachedBBSAPI(verify, channel)

@app.get("/bbs/result")
def write_bbs(request: Request, name: str = "", message: str = "", seed:Union[str, None] = "", channel:Union[str, None]="main", verify:Union[str, None]="false", yuki: Union[str] = Cookie(None)):
    if not(checkCookie(yuki)):
        return redirect("/")
    if 'Google-Apps-Script' in str(request.scope["headers"][1][1]):
        raise UnallowedBot("GASのBotは許可されていません")
      
    params = {
      'name': urllib.parse.quote(name),
      'message': urllib.parse.quote(message),
      'seed': urllib.parse.quote(seed),
      'channel': urllib.parse.quote(channel),
      'verify': urllib.parse.quote(verify),
      'info': urllib.parse.quote(getInfo(request)),
      'serververify': getVerifyCode()
    }
  
    url_querys = ''
    for key, value in params.items():
      url_querys += f'{key}={value}&'

    if url_querys != '':
      url_querys = '?' + url_querys[:-1]
      
    t = requests.get(f"{url}bbs/result" + url_querys, cookies={"yuki": "True"}, allow_redirects=False)
    if t.status_code != 307:
        return HTMLResponse(no_robot_meta_tag + t.text.replace('AutoLink(xhr.responseText);', 'urlConvertToLink(xhr.responseText);') + getSource('bbs'))
        
    return redirect(f"/bbs?name={urllib.parse.quote(name)}&seed={urllib.parse.quote(seed)}&channel={urllib.parse.quote(channel)}&verify={urllib.parse.quote(verify)}")

@cache(seconds=120)
def getCachedBBSHow():
    return requests.get(f"{url}bbs/how").text

@app.get("/bbs/how", response_class=PlainTextResponse)
def view_commonds(request: Request, yuki: Union[str] = Cookie(None)):
    if not(checkCookie(yuki)):
        return redirect("/")
    return getCachedBBSHow()



@app.get("/info", response_class=HTMLResponse)
def viewlist(response: Response, request: Request, yuki: Union[str] = Cookie(None)):
    if not(checkCookie(yuki)):
        return redirect("/")
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    
    return template("info.html", {"request": request, "Youtube_API": invidious_api.video[0], "Channel_API": invidious_api.channel[0], "comments": invidious_api.comments[0]})

@app.get("/reset", response_class=PlainTextResponse)
def home():
    global url, invidious_api
    url = requests.get('https://raw.githubusercontent.com/yuto1106110/yuto-yuki-youtube-1/main/APItati', headers=getRandomUserAgent()).text.rstrip()
    invidious_api = InvidiousAPI()
    return 'Success'

@app.get("/version", response_class=PlainTextResponse)
def displayVersion():
    return str({'version': version, 'new_instance_version': new_instance_version})

@app.get("/api/update", response_class=PlainTextResponse)
def updateAllAPI():
  global invidious_api
  return str((invidious_api := InvidiousAPI()).info())

@app.get("/api/{api_name}", response_class=PlainTextResponse)
def displayAPI(api_name: str):
  
  match api_name:
    case 'all':
      api_value = invidious_api.info()
        
    case 'video':
      api_value = invidious_api.video
  
    case 'search':
      api_value = invidious_api.search
  
    case 'channel':
      api_value = invidious_api.channel
  
    case 'comments':
      api_value = invidious_api.comments

    case 'playlist':
      api_value = invidious_api.playlist
      
    case _:
      api_value = f'API Name Error: {api_name}'
        
  return str(api_value)
    
@app.get("/api/{api_name}/next", response_class=PlainTextResponse)
def rotateAPI(api_name: str):
  match api_name:
    case 'video':
      updateList(invidious_api.video, invidious_api.video[0])
  
    case 'search':
      updateList(invidious_api.search, invidious_api.search[0])
  
    case 'channel':
      updateList(invidious_api.channel, invidious_api.channel[0])
  
    case 'comments':
      updateList(invidious_api.comments, invidious_api.comments[0])

    case 'playlist':
      updateList(invidious_api.playlist, invidious_api.playlist[0])

    case _:
      return f'API Name Error: {api_name}'
        
  return 'Finish'
    
@app.get("/api/video/check", response_class=PlainTextResponse)
def displayCheckVideo():
    return str(invidious_api.check_video)

@app.get("/api/video/check/toggle", response_class=PlainTextResponse)
def toggleVideoCheck():
    global invidious_api
    invidious_api.check_video = not invidious_api.check_video
    return f'{not invidious_api.check_video} to {invidious_api.check_video}'
  
@app.get("/proxy", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("proxy.html", {"request": request})
      
@app.get("/rammer", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("rammerhead.html", {"request": request})
  
@app.get("/shadow", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("shadow.html", {"request": request})

@app.get("/inbox", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("inbox.html", {"request": request})
  
@app.get("/help", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("help.html", {"request": request})
  
@app.get("/proxypage", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("game.html", {"request": request})

@app.get("/url", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("url.html", {"request": request})

@app.get("/light", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("light.html", {"request": request})
@app.get("/sitsumon", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("otoiawase.html", {"request": request})
@app.get("/news", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("news.html", {"request": request})
@app.get("/space", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("space.html", {"request": request})
@app.get("/update", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("settings.html", {"request": request})
@app.get("/others", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("others.html", {"request": request})
@app.get("/qanda", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("Q&A.html", {"request": request})
@app.get("/1v1lol", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("1v1lol.html", {"request": request})
@app.get("/drive", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("drive.html", {"request": request})
@app.get("/paper", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("paper.html", {"request": request})
@app.get("/snow", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("snow.html", {"request": request})
@app.get("/game", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("proxy.html", {"request": request})
@app.get("/set", response_class=HTMLResponse)
def list_page(response: Response, request: Request):
    return template("set.html", {"request": request})



@app.exception_handler(500)
def error500(request: Request, __):
    return template("error.html", {"request": request, "context": '500 Internal Server Error'}, status_code=500)
  
@app.exception_handler(404)
def error404(request: Request, __):
    return template("error.html", {"request": request, "context": '404 Error、あれれ'}, status_code=404)


@app.exception_handler(APITimeoutError)
def apiWait(request: Request, exception: APITimeoutError):
    return template("apiTimeout.html", {"request": request}, status_code=504)

@app.exception_handler(UnallowedBot)
def returnToUnallowedBot(request: Request, exception: UnallowedBot):
    return template("error.html", {"request": request, "context": '403 Forbidden'}, status_code=403)
