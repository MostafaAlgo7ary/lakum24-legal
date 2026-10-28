import os
import requests
import feedparser
from bs4 import BeautifulSoup
from moviepy.editor import ImageClip
from PIL import Image, ImageDraw, ImageFont
import io
import time

# --- الإعدادات ---
CLIENT_KEY = os.environ.get('TIKTOK_CLIENT_KEY')
CLIENT_SECRET = os.environ.get('TIKTOK_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('TIKTOK_REFRESH_TOKEN')

def get_access_token():
    url = "https://open.tiktokapis.com/v2/oauth/token/"
    payload = {
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = requests.post(url, data=payload, headers=headers)
    if response.status_code == 200:
        return response.json().get('access_token')
    return None

def get_news_data():
    # جلب الأخبار من خلاصة RSS
    url = "https://news.google.com/rss/search?q=أخبار+عامة&hl=ar&gl=EG&ceid=EG:ar"
    feed = feedparser.parse(url)
    if not feed.entries:
        return None
    entry = feed.entries[0]
    
    # محاولة استخراج صورة من رابط الخبر
    image_url = None
    try:
        article_resp = requests.get(entry.link, timeout=10)
        soup = BeautifulSoup(article_resp.text, 'html.parser')
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image_url = og_image['content']
    except Exception:
        pass
    
    # إذا لم توجد صورة، استخدم صورة افتراضية
    if not image_url:
        image_url = "https://picsum.photos/1080/1920" # صورة عشوائية
        
    return {"title": entry.title, "image_url": image_url}

def create_video_from_image(title, image_url, output_path="output_video.mp4"):
    # تحميل الصورة
    img_resp = requests.get(image_url, timeout=10)
    img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
    img = img.resize((1080, 1920)) # مقاس 9:16 لتيك توك
    
    # إضافة النص على الصورة
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
    except:
        font = ImageFont.load_default()
    
    # تقسيم النص لأسطر متعددة
    lines = []
    words = title.split()
    current_line = ""
    for word in words:
        test_line = current_line + word + " "
        if draw.textlength(test_line, font=font) < 900:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word + " "
    lines.append(current_line)
    
    y_text = 1500
    for line in lines:
        draw.text((50, y_text), line, font=font, fill="white", stroke_width=2, stroke_fill="black")
        y_text += 80

    # إنشاء فيديو من الصورة (ثابت لمدة 5 ثوانٍ)
    clip = ImageClip(img).set_duration(5)
    clip.write_videofile(output_path, fps=24, codec='libx264', audio=False)
    return output_path

def upload_to_tiktok(access_token, video_path, title):
    init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    video_size = os.path.getsize(video_path)
    payload = {
        "post_info": {
            "title": title,
            "privacy_level": "SELF_ONLY",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1
        }
    }
    
    init_resp = requests.post(init_url, json=payload, headers=headers)
    if init_resp.status_code != 200:
        print("Init Error:", init_resp.text)
        return
        
    upload_url = init_resp.json()['data']['upload_url']
    publish_id = init_resp.json()['data']['publish_id']
    
    with open(video_path, 'rb') as f:
        video_data = f.read()
        
    upload_headers = {
        "Content-Type": "video/mp4",
        "Content-Length": str(video_size),
        "Content-Range": f"bytes 0-{video_size-1}/{video_size}"
    }
    
    upload_resp = requests.put(upload_url, data=video_data, headers=upload_headers)
    if upload_resp.status_code in [200, 201, 206]:
        print(f"Video uploaded successfully! Publish ID: {publish_id}")
    else:
        print("Upload Error:", upload_resp.text)

if __name__ == "__main__":
    print("Starting TikTok News Bot...")
    token = get_access_token()
    if token:
        news = get_news_data()
        if news:
            print(f"Latest News: {news['title']}")
            video_file = create_video_from_image(news['title'], news['image_url'])
            upload_to_tiktok(token, video_file, news['title'])
        else:
            print("No news found.")
    else:
        print("Failed to get access token.")
