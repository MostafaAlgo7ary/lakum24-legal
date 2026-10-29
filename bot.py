import os
import requests
import feedparser
from bs4 import BeautifulSoup
from moviepy.editor import ImageClip, AudioFileClip
from PIL import Image
import io
import numpy as np
import re
import sys
from groq import Groq

# --- الإعدادات الأساسية ---
CLIENT_KEY = os.environ.get('TIKTOK_CLIENT_KEY')
CLIENT_SECRET = os.environ.get('TIKTOK_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('TIKTOK_REFRESH_TOKEN')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')

# --- الإعدادات القادمة من GitHub Actions ---
NEWS_URL = os.environ.get('NEWS_URL', '').strip()
SOURCE_URL = os.environ.get('SOURCE_URL', '').strip()
PRIVACY_LEVEL = os.environ.get('PRIVACY_LEVEL', 'SELF_ONLY').strip()
KEYWORD_FILTER = os.environ.get('KEYWORD_FILTER', '').strip()
ENABLE_AUDIO = os.environ.get('ENABLE_AUDIO', 'true').strip().lower() == 'true'

CAPTION_PREFIX = os.environ.get('CAPTION_PREFIX', '').strip()
if CAPTION_PREFIX.lower() == 'none':
    CAPTION_PREFIX = ''

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
                        "content": "أنت محرر وصانع محتوى رياضي وعام محترف على تيك توك. مهمتك هي قراءة الخبر التالي وإعادة صياغته وترجمته إلى لغة عربية فصحى قوية وسليمة. استخدم أسلوباً صحفياً احترافياً ومفهوماً. يجب أن يحتوي النص الجديد على كل المعلومات والتفاصيل الهامة. استخدم تنسيقاً جذاباً (مثل النقاط والإيموجي). تحذير هام جداً: يُمنع منعاً باتاً استخدام أي رموز تنسيق مثل النجمة (**) في النص الأساسي. يُمنع منعاً باتاً ذكر اسم أي موقع أو مصدر إخباري. لا تكتب أي مقدمات. في النهاية، أضف 10 هاشتاجات دقيقة جداً ومرتبطة حصرياً بموضوع الخبر. قاعدة إجبارية للهاشتاجات: إذا كان الهاشتاج يتكون من أكثر من كلمة، يجب ربط الكلمات بعلامة الشرطة السفلية ( _ ) وليس بمسافة."
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
            cleaned_result = re.sub(r'\*+', '', result)
            print(f"✅ Success with {model_name}!")
            return cleaned_result.strip()
        except Exception as e:
            print(f"❌ Model {model_name} failed: {e}")
            continue
    return None

def extract_news_links_from_html(url):
    print(f"Scraping links from HTML page: {url}")
    links = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if '/story/' in href:
                if href.startswith('http'):
                    links.append(href)
                elif href.startswith('/'):
                    links.append(f"https://www.youm7.com{href}")
    except Exception as e:
        print(f"Error extracting links from {url}: {e}")
    return links

def keyword_matches(title, keyword):
    if not keyword:
        return True
    if keyword in title:
        return True
    if keyword.startswith('ال') and keyword[2:] in title:
        return True
    return False

def get_candidate_urls(source_url, posted_urls, limit=15):
    urls = []
    if 'almasryalyoum.com/rss' in source_url:
        try:
            feed = feedparser.parse(source_url)
            for entry in feed.entries:
                if entry.link not in posted_urls:
                    urls.append(entry.link)
                if len(urls) >= limit:
                    break
        except Exception as e:
            print(f"Error reading RSS {source_url}: {e}")
            
    elif 'youm7.com/Section' in source_url:
        links = extract_news_links_from_html(source_url)
        for link in links:
            if link not in posted_urls:
                urls.append(link)
            if len(urls) >= limit:
                break
    return urls

def scrape_full_article(article_url, fallback_text=""):
    print(f"Scraping full article from: {article_url}")
    image_url = None
    text_content = ""
    title = ""
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(article_url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')

        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content']
        elif soup.title:
            title = soup.title.string

        if not keyword_matches(title, KEYWORD_FILTER):
            print(f"❌ Keyword '{KEYWORD_FILTER}' not found in title. Skipping this article.")
            return None, None, None

        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image_url = og_image['content']
        
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
            text_content = fallback_text
            
    except Exception as e:
        print(f"Error scraping article: {e}")
        text_content = fallback_text

    if not image_url:
        image_url = "https://picsum.photos/1080/1920"
        
    return title, text_content, image_url

def create_video_from_image(image_url, output_path="output_video.mp4"):
    print("Downloading image...")
    img_resp = requests.get(image_url, timeout=15)
    img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")

    # --- التعديل الجديد: وضع الصورة في منتصف خلفية سوداء بدون تمدد ---
    target_w, target_h = 1080, 1920
    background = Image.new("RGB", (target_w, target_h), (0, 0, 0)) # خلفية سوداء
    
    # حساب أبعاد الصورة الجديدة مع الحفاظ على التناسب
    img_w, img_h = img.size
    ratio = min(target_w / img_w, target_h / img_h)
    new_w = int(img_w * ratio)
    new_h = int(img_h * ratio)
    
    img = img.resize((new_w, new_h), Image.LANCZOS)
    
    # وضع الصورة في المنتصف
    paste_x = (target_w - new_w) // 2
    paste_y = (target_h - new_h) // 2
    background.paste(img, (paste_x, paste_y))
    # -------------------------------------------------------------------

    print("Creating 5-second video with zoom effect...")
    clip = ImageClip(np.array(background)).set_duration(5)
    clip = clip.resize(lambda t: 1 + 0.05 * t)
    
    if ENABLE_AUDIO:
        print("Adding background audio...")
        try:
            audio_url = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"
            audio_resp = requests.get(audio_url, timeout=15)
            with open("bg_music.mp3", "wb") as f:
                f.write(audio_resp.content)
            audioclip = AudioFileClip("bg_music.mp3").subclip(0, 5)
            clip = clip.set_audio(audioclip)
        except Exception as e:
            print(f"⚠️ Could not add audio (continuing without it): {e}")
    else:
        print("Audio is disabled. Creating silent video.")

    clip.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac')
    return output_path

def upload_to_tiktok_direct(access_token, video_path, caption):
    print(f"Uploading video via Direct Post (Privacy: {PRIVACY_LEVEL})...")
    init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    video_size = os.path.getsize(video_path)
    
    payload = {
        "post_info": {
            "title": caption[:2200], 
            "privacy_level": PRIVACY_LEVEL,
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
        if "spam_risk_too_many_posts" in init_resp.text:
            return "SPAM"
        return False
        
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
        print(f"✅ Video uploaded successfully! Publish ID: {publish_id}")
        return True
    else:
        print("Upload Error:", upload_resp.text)
        return False

def save_to_history(url):
    with open('posted_history.txt', 'a', encoding='utf-8') as f:
        f.write(url + '\n')
    print("History updated.")

if __name__ == "__main__":
    print("Starting TikTok News Bot...")
    
    if not CLIENT_KEY or not CLIENT_SECRET or not REFRESH_TOKEN or not GROQ_API_KEY:
        print("❌ Error: One or more secrets are missing in GitHub!")
        sys.exit(1)
    else:
        token = get_access_token()
        if token:
            uploaded_successfully = False

            if NEWS_URL:
                print("Using manual News Article URL provided by user.")
                title, text_to_summarize, image_url = scrape_full_article(NEWS_URL, "خبر جديد")
                if title and text_to_summarize:
                    final_caption = summarize_with_groq(title, text_to_summarize)
                    if not final_caption:
                        clean_text = re.sub(r'\|.*', '', text_to_summarize).strip()
                        final_caption = f"{clean_text[:800]}...\n\n#أخبار #تيك_توك"
                    if CAPTION_PREFIX:
                        final_caption = f"{CAPTION_PREFIX}\n\n{final_caption}"
                    
                    video_file = create_video_from_image(image_url)
                    upload_result = upload_to_tiktok_direct(token, video_file, final_caption)
                    
                    if upload_result == True:
                        save_to_history(NEWS_URL)
                        uploaded_successfully = True
                    elif upload_result == "SPAM":
                        print("🛑 TikTok SPAM block detected. Exiting immediately to save resources.")
                        sys.exit(0)
                else:
                    print("❌ Failed to scrape the provided news URL or keyword didn't match.")

            else:
                print("Looking for the latest news from sources...")
                posted_urls = set()
                if os.path.exists('posted_history.txt'):
                    with open('posted_history.txt', 'r', encoding='utf-8') as f:
                        posted_urls = set(line.strip() for line in f)

                sources_to_check = []
                if SOURCE_URL:
                    sources_to_check = [SOURCE_URL]
                else:
                    if os.path.exists('sources.txt'):
                        with open('sources.txt', 'r', encoding='utf-8') as f:
                            sources_to_check = [line.strip() for line in f if line.strip().startswith('http')]
                    
                    pointer = 0
                    if os.path.exists('source_pointer.txt'):
                        with open('source_pointer.txt', 'r', encoding='utf-8') as f:
                            try:
                                pointer = int(f.read().strip())
                            except:
                                pointer = 0
                    
                    if sources_to_check:
                        sources_to_check = sources_to_check[pointer:] + sources_to_check[:pointer]

                for source_url in sources_to_check:
                    print(f"Checking source: {source_url}")
                    
                    candidate_urls = get_candidate_urls(source_url, posted_urls, limit=15)
                    
                    if not candidate_urls:
                        print("⚠️ No new unposted articles found in this source.")
                        continue
                        
                    for article_url in candidate_urls:
                        title, text_to_summarize, image_url = scrape_full_article(article_url, "")
                        
                        if title and text_to_summarize:
                            print(f"✅ Processing article: {title}")
                            final_caption = summarize_with_groq(title, text_to_summarize)
                            
                            if not final_caption:
                                print("⚠️ Groq failed. Using fallback.")
                                clean_text = re.sub(r'\|.*', '', text_to_summarize).strip()
                                final_caption = f"{clean_text[:800]}...\n\n#أخبار #تيك_توك"
                            
                            if CAPTION_PREFIX:
                                final_caption = f"{CAPTION_PREFIX}\n\n{final_caption}"
                            
                            video_file = create_video_from_image(image_url)
                            
                            upload_result = upload_to_tiktok_direct(token, video_file, final_caption)
                            
                            if upload_result == True:
                                save_to_history(article_url)
                                uploaded_successfully = True
                                
                                if not SOURCE_URL:
                                    with open('source_pointer.txt', 'w', encoding='utf-8') as f:
                                        current_idx = sources_to_check.index(source_url)
                                        f.write(str(current_idx))
                                
                                break 
                            elif upload_result == "SPAM":
                                print("🛑 TikTok SPAM block detected. Exiting immediately to save resources.")
                                sys.exit(0) 
                    
                    if uploaded_successfully:
                        break

            if not uploaded_successfully:
                print("❌ Failed to find a suitable news article or upload failed.")
        else:
            print("Failed to get access token.")
