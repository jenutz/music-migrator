import json
def test():
    from yandex_music import Client
    with open("yandex.key", "r") as file:
        API_KEY = file.read().rstrip()
    client = Client(API_KEY).init()
    id = 52650274
    songs = client.tracks(id)[0]
    # print((songs))
    # print(dir(songs))
    # print(songs['title'])
    print(norm_yd_track(songs))

    # print(songs['albums'][0].get_cover_url('200x200'))


def norm_yd_track(track):
    return {
        'title': track['title'],
        'artists': ','.join(str(e['name']) for e in track['artists']),
        'album': track['albums'][0]['title'],
        'thumbnail' : track['albums'][0].get_cover_url('200x200'),
        'length_s' :track['duration_ms']
    }


def test2():
    from ytmusicapi import YTMusic
    ytmusic = YTMusic('browser.json')
    # song = ytmusic.get_song(videoId="FJx2x0p1U-M")
    song = ytmusic.get_song(videoId="iIUjpatokVs")
    # print(json.dumps(song))
    print(norm_yt_track(song))


    # print(song['title'])
    # print(song['artist'])
    # print(song['album'])
    # thumbnails = song["videoDetails"]["thumbnail"]["thumbnails"]
    # print(thumbnails[0]['url'])




test()

