import os
import requests
import feedparser
from bs4 import BeautifulSoup
from moviepy.editor import ImageClip
from PIL import Image, ImageDraw, ImageFont
import io
import arabic_reshaper
from bidi.algorithm import get_display

# --- الإعدادات ---
CLIENT_KEY = os.environ.get('TIKTOK_CLIENT_KEY')
CLIENT_SECRET = os.environ.get('TIKTOK_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('TIKTOK_REFRESH_TOKEN')
NEWS_URL = os.environ.get('NEWS_URL', '').strip()

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
    else:
        # طباعة الخطأ الحقيقي عشان نعرف السبب
        print(f"❌ Token Error Status: {response.status_code}")
        print(f"❌ Token Error Details: {response.text}")
        return None

def fix_arabic(text):
    reshaped_text = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)
    return bidi_text

def get_news_data():
    title = ""
    text_content = ""
    image_url = None

    if NEWS_URL:
        print(f"Fetching specific URL: {NEWS_URL}")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            resp = requests.get(NEWS_URL, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')

            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                image_url = og_image['content']
            
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title['content']
            elif soup.title:
                title = soup.title.string

            paragraphs = soup.find_all('p')
            article_text = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 30])
            if article_text:
                text_content = article_text[:400] + "..."
            else:
                text_content = "لم يتم العثور على نص كافٍ في هذا الرابط."

        except Exception as e:
            print("Error scraping URL:", e)
            return None
    else:
        print("Fetching automatic news from RSS...")
        url = "https://news.google.com/rss/search?q=أخبار+عامة&hl=ar&gl=EG&ceid=EG:ar"
        feed = feedparser.parse(url)
        if not feed.entries:
            return None
        entry = feed.entries[0]
        title = entry.title
        text_content = entry.summary if hasattr(entry, 'summary') else title

        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            article_resp = requests.get(entry.link, headers=headers, timeout=10)
            soup = BeautifulSoup(article_resp.text, 'html.parser')
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                image_url = og_image['content']
        except Exception:
            pass

    if not image_url:
        image_url = "https://picsum.photos/1080/1920"

    return {"title": title, "text": text_content, "image_url": image_url}

def create_video_from_image(title, text, image_url, output_path="output_video.mp4"):
    print("Downloading image...")
    img_resp = requests.get(image_url, timeout=15)
    img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
    
    img = img.resize((1080, 1920))
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 150))
    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')

    draw = ImageDraw.Draw(img)
    
    font_path = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"
    try:
        title_font = ImageFont.truetype(font_path, 70)
        text_font = ImageFont.truetype(font_path, 55)
    except:
        print("Warning: Arabic font not found, using default.")
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()

    fixed_title = fix_arabic(title)
    fixed_text = fix_arabic(text)

    def wrap_text(text, font, max_width, draw):
        lines = []
        words = text.split()
        current_line = ""
        for word in words:
            test_line = current_line + word + " "
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
            if width <= max_width:
                current_line = test_line
            else:
                lines.append(current_line.strip())
                current_line = word + " "
        if current_line:
            lines.append(current_line.strip())
        return lines

    y_text = 300
    title_lines = wrap_text(fixed_title, title_font, 950, draw)
    for line in title_lines:
        draw.text((60, y_text), line, font=title_font, fill="yellow")
        y_text += 90

    y_text += 50
    text_lines = wrap_text(fixed_text, text_font, 950, draw)
    for line in text_lines:
        if y_text > 1800:
            break
        draw.text((60, y_text), line, font=text_font, fill="white")
        y_text += 80

    print("Creating 5-second video...")
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
            "title": title[:150],
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
    
    # التأكد إن المتغيرات موجودة
    if not CLIENT_KEY or not CLIENT_SECRET or not REFRESH_TOKEN:
        print("❌ Error: One or more secrets are missing in GitHub!")
    else:
        token = get_access_token()
        if token:
            news = get_news_data()
            if news and news.get('title'):
                print(f"Title: {news['title']}")
                video_file = create_video_from_image(news['title'], news['text'], news['image_url'])
                upload_to_tiktok(token, video_file, news['title'])
            else:
                print("Failed to get news data.")
        else:
            print("Failed to get access token.")
