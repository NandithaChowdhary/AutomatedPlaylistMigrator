#sample\app\forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length

class InfoForm(FlaskForm):
    youtube_playlist = StringField("YouTube Playlist URL:", validators=[DataRequired()])
    spotify_playlist_name = StringField("New Spotify Playlist name:", validators=[DataRequired()])
    submit = SubmitField("Submit")
