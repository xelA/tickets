def detect_file(file):
    image = ["jpeg", "jpg", "png", "gif"]
    video = ["mp4"]
    music = ["mp3"]
    file_ext = file["filename"].split(".")[-1]
    if file_ext in image:
        return f'<div class="image-container"><img class="upload" src="{file["content"]}" alt="{file["filename"]}" data-enlargable></div>'
    elif file_ext in video:
        return f'<div class="video-container"><video class="upload" width="420" controls><source src="{file["content"]}" type="video/mp4"></video></div>'
    elif file_ext in music:
        return f'<div class="music-container"><audio controls><source src="{file["content"]}" type="audio/mpeg"></audio></div>'
    else:
        return f'<div class="file-container"><a class="upload" href="{file["content"]}" alt="{file["filename"]}">📂 {file["filename"]}</a></div>'
