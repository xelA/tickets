from markupsafe import Markup

from utils.discord_objects import safe_url


def detect_file(file: dict) -> Markup:
    """ Render an attachment as an image, video, audio player or file link based on its extension """
    image = ["jpeg", "jpg", "png", "gif", "webp"]
    video = ["mp4", "webm", "mov"]
    music = ["mp3", "ogg", "wav"]

    filename = str(file.get("filename") or "file")
    url = safe_url(file.get("content"))
    if not url:
        return Markup('<div class="file-container"><span class="upload">📂 {}</span></div>').format(filename)

    file_ext = filename.split(".")[-1].lower()
    if file_ext in image:
        return Markup('<div class="image-container"><img class="upload" src="{}" alt="{}" data-enlargable></div>').format(url, filename)
    if file_ext in video:
        return Markup('<div class="video-container"><video class="upload" controls preload="metadata"><source src="{}"></video></div>').format(url)
    if file_ext in music:
        return Markup('<div class="music-container"><audio controls preload="metadata"><source src="{}"></audio></div>').format(url)
    return Markup('<div class="file-container"><a class="upload" href="{}" target="_blank" rel="noopener noreferrer">📂 {}</a></div>').format(url, filename)
