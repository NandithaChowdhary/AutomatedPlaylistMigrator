
import re
import googleapiclient.discovery
from flask import (
    abort,
    Flask,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
import json
import requests
from urllib.parse import urlencode
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length

app = Flask(__name__)
app.secret_key = ""


AUTHORIZATION_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
BASE_URI = "http://127.0.0.1:5000"

DEVELOPER_KEY = ""

SPOTIFY_CLIENT_ID = ""
SPOTIFY_CLIENT_SECRET = ""
SPOTIFY_REDIRECT_URI = ""

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
ME_URL = "https://api.spotify.com/v1/me"


class InfoForm(FlaskForm):
    youtube_playlist = StringField(
        "YouTube Playlist URL:", validators=[DataRequired()])
    spotify_playlist_name = StringField(
        "New Spotify Playlist name:", validators=[DataRequired()]
    )
    submit = SubmitField("Migrate")


form = None


@app.route("/", methods=["GET", "POST"])
def index():
    global form
    form = InfoForm()
    if form.validate_on_submit():
        return redirect(BASE_URI + "/login")
    return render_template("index.html", form=form)


@app.route("/<loginout>")
def login(loginout):
    # Request authorization from user
    scope = "user-read-private user-read-email playlist-modify-public playlist-modify-private"

    if loginout == "logout":
        payload = {
            "client_id": SPOTIFY_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": SPOTIFY_REDIRECT_URI,
            "scope": scope,
            "show_dialog": True,
        }
    elif loginout == "login":
        payload = {
            "client_id": SPOTIFY_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": SPOTIFY_REDIRECT_URI,
            "scope": scope,
        }
    else:
        abort(404)

    res = make_response(redirect(f"{AUTH_URL}/?{urlencode(payload)}"))

    return res


@app.route("/callback")
def callback():
    error = request.args.get("error")
    code = request.args.get("code")
    stored_state = request.cookies.get("spotify_auth_state")

    # Request tokens with code we obtained
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
    }

    res = requests.post(
        TOKEN_URL, auth=(SPOTIFY_CLIENT_ID,
                         SPOTIFY_CLIENT_SECRET), data=payload
    )
    res_data = res.json()

    if res_data.get("error") or res.status_code != 200:
        app.logger.error(
            "Failed to receive token: %s",
            res_data.get("error", "No error information received."),
        )
        abort(res.status_code)

    session["tokens"] = {
        "access_token": res_data.get("access_token"),
        "refresh_token": res_data.get("refresh_token"),
    }

    return redirect(url_for("me"))


@app.route("/refresh")
def refresh():
    """Refresh access token."""

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": session.get("tokens").get("refresh_token"),
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    res = requests.post(
        TOKEN_URL,
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        data=payload,
        headers=headers,
    )
    res_data = res.json()

    session["tokens"]["access_token"] = res_data.get("access_token")

    return json.dumps(session["tokens"])


@app.route("/me")
def me():
    api_service_name = "youtube"
    api_version = "v3"

    youtube = googleapiclient.discovery.build(
        api_service_name, api_version, developerKey = DEVELOPER_KEY)
    playlist = str(form.youtube_playlist.data)
    playlistid = re.findall("list=(.*)", playlist)[0]

    req = youtube.playlistItems().list(
        part="snippet,contentDetails", maxResults=50, playlistId=playlistid
    )
    res = req.execute()
    nextPageToken = res.get("nextPageToken")

    while "nextPageToken" in res:
        nextPage = (
            youtube.playlistItems()
            .list(
                part="snippet,contentDetails",
                playlistId=playlistid,
                maxResults="50",
                pageToken=nextPageToken,
            )
            .execute()
        )
        res["items"] += nextPage["items"]

        if "nextPageToken" not in nextPage:
            res.pop("nextPageToken", None)
        else:
            nextPageToken = nextPage["nextPageToken"]
    videos = res["items"]
    # Check for tokens
    if "tokens" not in session:
        app.logger.error("No tokens in session.")
        abort(400)

    headers = {
        "Authorization": f"Bearer {session['tokens'].get('access_token')}"}
    res = requests.get(ME_URL, headers=headers)
    res_data = res.json()
    payload = {"name": form.spotify_playlist_name.data, "public": False}
    user_id = res_data["id"]
    req_playlist = requests.post(
        "https://api.spotify.com/v1/users/" + user_id + "/playlists",
        json=payload,
        headers=headers,
    )
    new_playlist_url = req_playlist.json()["id"]
    new_playlist_link = req_playlist.json()

    for video in videos:
        song_video = video["snippet"]["title"]
        song_video = song_video.lower()
        if song_video == "private video":
            continue
        song = re.findall("^[^\(]*", song_video)[0]
        song = re.findall("^[^\[]*", song)[0]
        song = re.findall("^[^|]*", song)[0]
        song = song.replace("&", " ")
        song = song.replace("ft.", " ")
        songg = song.replace("feat.", " ")
        payload = {"q": songg, "limit": "1", "type": "track"}
        song = requests.get(
            "https://api.spotify.com/v1/search", params=payload, headers=headers
        )
        song = song.json()
        try:
            song_url = song["tracks"]["items"][0]["uri"]
            payload = {"uris": [song_url]}
            add_songs_to_playlist = requests.post(
                "https://api.spotify.com/v1/playlists/" + new_playlist_url + "/tracks",
                json=payload,
                headers=headers,
            )
        except:
            continue

    if res.status_code != 200:
        app.logger.error(
            "Failed to get profile info: %s",
            res_data.get("error", "No error message returned."),
        )
        abort(res.status_code)

    return render_template(
        "me.html",
        data=res_data,
        playlist=new_playlist_link,
        tokens=session.get("tokens"),
    )


if __name__ == "__main__":
    app.run(debug=True)
