from ytmusicapi import YTMusic

# Загрузите данные авторизации
ytmusic = YTMusic('browser.json')


# Получение списка песен из библиотеки
songs = ytmusic.get_playlist("LM", 100000)['tracks']

# Вывод информации о песнях
for song in songs:
    print(f"Название: {song['title']}")
    print(f"Исполнитель: {', '.join(artist['name'] for artist in song['artists'])}")
    print(f"Трек ID: {song['videoId']}")
    print(f"Песня понравилась: {song['likeStatus']}")
    print('-' * 40)
