import os
import requests
import feedparser
from bs4 import BeautifulSoup
from moviepy.editor import ImageClip
from PIL import Image
import io
import numpy as np
import re
from groq import Groq

# --- الإعدادات ---
CLIENT_KEY = os.environ.get('TIKTOK_CLIENT_KEY')
CLIENT_SECRET = os.environ.get('TIKTOK_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('TIKTOK_REFRESH_TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
NEWS_URL = os.environ.get('NEWS_URL', '').strip()

# تهيئة عميل Groq
groq_client = Groq(api_key=GROQ_API_KEY)

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
        print(f"❌ Token Error: {response.text}")
        return None

def summarize_with_groq(title, text):
    print("Generating translated & rewritten article with Groq...")
    
    truncated_text = text[:4000].strip()
    if not truncated_text:
        truncated_text = title

    models_to_try = [
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
        "qwen/qwen3-32b",
        "meta-llama/llama-4-maverick-17b-128e-instruct"
    ]

    for model_name in models_to_try:
        print(f"🔄 Trying model: {model_name}")
        try:
            chat_completion = groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "أنت محرر وصانع محتوى رياضي محترف على تيك توك. مهمتك هي قراءة الخبر التالي (حتى لو كان مكتوباً بالإنجليزية) وإعادة صياغته وترجمته إلى لغة عربية فصحى قوية وسليمة. استخدم أسلوباً صحفياً رياضياً احترافياً ومفهوماً، واستخدم المصطلحات الرياضية الدارجة (مثل: بطاقة حمراء، ركلات ترجيح، إيقاف، بدلاً من الترجمة الحرفية). يجب أن يحتوي النص الجديد على كل المعلومات والتفاصيل الهامة. استخدم تنسيقاً جذاباً (مثل النقاط والإيموجي). تحذير هام جداً: يُمنع منعاً باتاً استخدام أي رموز تنسيق مثل النجمة (**) في النص الأساسي، اكتب نصاً عادياً فقط. يُمنع منعاً باتاً ذكر اسم أي موقع أو مصدر إخباري. لا تكتب أي مقدمات. في النهاية، أضف 10 هاشتاجات دقيقة جداً ومرتبطة حصرياً بموضوع الخبر (تجنب الهاشتاجات العامة جداً). قاعدة إجبارية للهاشتاجات: إذا كان الهاشتاج يتكون من أكثر من كلمة، يجب ربط الكلمات بعلامة الشرطة السفلية ( _ ) وليس بمسافة (مثال: #الدوري_الإنجليزي #بطولة_الكاراباو). ضع الهاشتاجات في سطر منفصل."
                    },
                    {
                        "role": "user",
                        "content": f"العنوان: {title}\n\nالنص الأصلي:\n{truncated_text}"
                    }
                ],
                model=model_name,
                temperature=0.6,
                max_tokens=1500,
            )
            result = chat_completion.choices[0].message.content
            
            # تنظيف النص من أي نجوم تسربت
            cleaned_result = re.sub(r'\*+', '', result)
            
            print(f"✅ Success with {model_name}!")
            return cleaned_result.strip()
            
        except Exception as e:
            print(f"❌ Model {model_name} failed: {e}")
            continue

    print("⚠️ All Groq models failed.")
    return None

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

            for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
                tag.decompose()

            article_body = soup.find('article') or soup.find('main') or soup.find('body')
            
            if article_body:
                paragraphs = article_body.find_all('p')
                article_text = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])
            else:
                article_text = ""

            if article_text:
                text_content = article_text
            else:
                text_content = soup.get_text(separator=' ', strip=True)

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

def create_video_from_image(image_url, output_path="output_video.mp4"):
    print("Downloading image...")
    img_resp = requests.get(image_url, timeout=15)
    img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
    
    img = img.resize((1080, 1920))

    print("Creating 5-second video...")
    clip = ImageClip(np.array(img)).set_duration(5)
    clip.write_videofile(output_path, fps=24, codec='libx264', audio=False)
    return output_path

def upload_to_tiktok(access_token, video_path, caption):
    init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    video_size = os.path.getsize(video_path)
    payload = {
        "post_info": {
            "title": caption[:2200], 
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
    
    if not CLIENT_KEY or not CLIENT_SECRET or not REFRESH_TOKEN or not GROQ_API_KEY:
        print("❌ Error: One or more secrets are missing in GitHub!")
    else:
        token = get_access_token()
        if token:
            news = get_news_data()
            if news and news.get('title'):
                print(f"Original Title: {news['title']}")
                
                final_caption = summarize_with_groq(news['title'], news['text'])
                
                if not final_caption:
                    print("⚠️ Groq failed. Using original text (cleaned) as fallback.")
                    clean_text = re.sub(r'\|.*', '', news['text']).strip()
                    final_caption = f"{clean_text[:800]}...\n\n#أخبار #تيك_توك"
                else:
                    print("✅ Groq succeeded!")

                print(f"Final Caption: \n{final_caption}")
                
                video_file = create_video_from_image(news['image_url'])
                upload_to_tiktok(token, video_file, final_caption)
            else:
                print("Failed to get news data.")
        else:
            print("Failed to get access token.")
