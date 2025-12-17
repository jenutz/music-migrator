import os
import sqlite3
from rapidfuzz import fuzz, process
from collections import namedtuple

Song = namedtuple(
    "Song",
    [
        "track_id",    # int or None
        "service_id",  # str or None (e.g., YouTube / Yandex ID)
        "title",       # str or None
        "artists",     # str or None
        "duration_s"   # int or None (duration in seconds)
    ]
)

def init_db(service: str):
    db_path = f"tracks_{service}.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tracks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ytid VARCHAR(20),
        ydid TEXT,
        title TEXT,
        duration_s INTEGER
    );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS artists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS track_artists (
        track_id INTEGER,
        artist_id INTEGER,
        PRIMARY KEY (track_id, artist_id),
        FOREIGN KEY (track_id) REFERENCES tracks(id),
        FOREIGN KEY (artist_id) REFERENCES artists(id)
    );
    ''')

    conn.commit()
    return conn


def get_songs(service):
    conn = sqlite3.connect(f"tracks_{service}.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(f'''
    SELECT 
    t.id AS track_id,
    t.{service}id as service_id,
    t.title,
    GROUP_CONCAT(a.name, ', ') AS artists,
    t.duration_s
    FROM tracks AS t
    INNER JOIN track_artists AS j ON j.track_id = t.id
    INNER JOIN artists AS a ON j.artist_id = a.id
    GROUP BY t.id, t.{service}id, t.title, t.duration_s;''')


    songs = cursor.fetchall()
    conn.close()
    res = [dict(row) for row in songs]
    return res

def pull_songs(service:str):
    if service == 'yd':
        pull_songs_yd()
    elif service == 'yt':
        pull_songs_yt()


def pull_songs_yt():
    from ytmusicapi import YTMusic
    ytmusic = YTMusic('browser.json')
    songs = ytmusic.get_playlist("LM", None)['tracks']

    conn = init_db('yt')
    cursor = conn.cursor()

    for song in reversed(songs):
        cursor.execute('''INSERT INTO tracks(ytid, title, duration_s) VALUES (?,?,?) RETURNING id''',
                       (song['videoId'], song['title'], song['duration_seconds'])) 
        song_id = cursor.fetchone()[0]
        for artist in song['artists']:
            cursor.execute('''
                        INSERT OR IGNORE INTO artists(name)
                        VALUES (?)''',
                           (artist['name'],))
            cursor.execute('''SELECT id FROM artists where name = ?''', (artist['name'],))
            artist_id = cursor.fetchone()[0]
            cursor.execute('''
                        INSERT INTO track_artists(track_id, artist_id)
                        VALUES (?, ?)''',
                           (song_id, artist_id))
    conn.commit()



def pull_songs_yd():
    from yandex_music import Client
    with open("yandex.key", "r") as file:
        API_KEY = file.read().rstrip()
    client = Client(API_KEY).init()
    songs = client.users_likes_tracks().fetch_tracks()


    conn = init_db('yd')
    cursor = conn.cursor()

    for song in reversed(songs):
        cursor.execute('''INSERT INTO tracks(ydid, title, duration_s) VALUES (?,?,?) RETURNING id''',
                       (song.id, song.title, song.duration_ms//1000)) 
        song_id = cursor.fetchone()[0]
        for artist in song.artists:
            cursor.execute('''
                        INSERT OR IGNORE INTO artists(name)
                        VALUES (?)''',
                           (artist.name,))
            cursor.execute('''SELECT id FROM artists where name = ?''', (artist.name,))
            artist_id = cursor.fetchone()[0]
            try:
                cursor.execute('''
                        INSERT INTO track_artists(track_id, artist_id)
                        VALUES (?, ?)''',
                               (song_id, artist_id))
            except sqlite3.IntegrityError as e:
                print(e)
    conn.commit()

def get_complement():
    yt = sqlite3.connect("tracks_yt.db")
    yd = sqlite3.connect("tracks_yd.db")

    yt_songs = yt.execute("""
    SELECT 
    t.id AS track_id,
    t.ytid as service_id,
    t.title,
    GROUP_CONCAT(a.name, ', ') AS artists,
    t.duration_s
    FROM tracks AS t
    INNER JOIN track_artists AS j ON j.track_id = t.id
    INNER JOIN artists AS a ON j.artist_id = a.id
    GROUP BY t.id, t.ytid, t.title, t.duration_s ORDER BY t.id DESC;""").fetchall()

    yd_songs = yd.execute("""
    SELECT 
    t.id AS track_id,
    t.ydid as service_id,
    t.title,
    GROUP_CONCAT(a.name, ', ') AS artists,
    t.duration_s
    FROM tracks AS t
    INNER JOIN track_artists AS j ON j.track_id = t.id
    INNER JOIN artists AS a ON j.artist_id = a.id
    GROUP BY t.id, t.ydid, t.title, t.duration_s ORDER BY t.id DESC;""").fetchall()


    yt_songs = [f"{remove_tags(e[2])} - {e[3]}".lower() for e in yt_songs]
    comp = []

    for song in yd_songs:
        song_str = f"{remove_tags(song[2])} - {song[3]}".lower()
        res = process.extractOne(song_str, yt_songs, scorer=fuzz.token_set_ratio)
        if res[1] < 85:
            comp.append(song)

    return [Song(*e) for e in comp]

def remove_tags(res):
    import re
    res = re.sub(r'\(Remastered \d{4}\)', '', res)
    res = re.sub(r'\(\d{4} Remaster\s*\)', '', res)
    pattern = r'[\(\[](?:digital|\d\d\d\d|master|official|music|video|audio|lyrics|lyric|hd|hq|remastered|visualizer)(?:\s+(?:digital|\d\d\d\d|master|official|music|video|audio|lyrics|lyric|hd|hq|remastered|visualizer))*[\)\]]'
    res = re.sub(pattern, '', res,  flags=re.IGNORECASE)
    pattern = r'(?i)\b(digital|\d\d\d\d|master|official|music|video|audio|lyrics|lyric|hd|hq|remastered|visualizer)\b'
    res = re.sub(pattern, '', res)
    res = re.sub(r'\s+', ' ', res)
    return res

def test():
    a= "аристократ - аквариум"
    a= "device - who's on the line"
    b= "device - who's on the line ( sound) (aor/melodic rock) - sebastian aor"
    print(process.extractOne(a,[b,], ))
    print(process.extractOne(a,[b,], scorer=fuzz.ratio))
    print(process.extractOne(a,[b,], scorer=fuzz.ratio))
    print(process.extractOne(a,[b,], scorer=fuzz.partial_ratio))
    print(process.extractOne(a,[b,], scorer=fuzz.token_sort_ratio))
    print(process.extractOne(a,[b,], scorer=fuzz.token_set_ratio))







if __name__ == '__main__':
    get_complement()
    # test()



