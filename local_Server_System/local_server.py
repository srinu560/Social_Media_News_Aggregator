import sqlite3
import feedparser
import random
from flask import Flask, jsonify, request
from flask_cors import CORS
from concurrent.futures import ThreadPoolExecutor

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app)

# --- Database Configuration ---
DATABASE = 'news.db'

# --- RSS Feed Configuration ---
# 'Indian News' is now a nested dictionary to handle languages
NEWS_FEEDS = {
    'Technology': {
        'TechCrunch': 'https://techcrunch.com/feed/',
        'Wired': 'https://www.wired.com/feed/rss',
    },
    'Business': {
        'Reuters Business': 'http://feeds.reuters.com/reuters/businessNews',
        'Wall Street Journal': 'https://feeds.a.dj.com/rss/RSSOpinion.xml'
    },
    'Entertainment': {
        'Variety': 'https://variety.com/feed/',
        'Deadline': 'https://deadline.com/feed/'
    },
    'Crime': {
        'NBC News Crime': 'https://www.nbcnews.com/id/15725623/device/rss/rss.xml'
    },
    'World News': {
        'BBC News': 'http://feeds.bbci.co.uk/news/rss.xml',
        'Reuters World': 'http://feeds.reuters.com/Reuters/worldNews'
    },
    'Indian News': {
        'English': {
            'Times of India': 'https://timesofindia.indiatimes.com/rssfeedstopstories.cms',
            'The Hindu': 'https://www.thehindu.com/news/national/feeder/default.rss',
            'NDTV': 'https://feeds.feedburner.com/ndtvnews-latest',
        },
        'Hindi': {
            'BBC Hindi': 'https://feeds.bbci.co.uk/hindi/rss.xml',
            'Dainik Jagran': 'https://www.jagran.com/rss/news/national.xml',
        },
        'Telugu': {
            'Sakshi': 'https://www.sakshi.com/rss',
            'TV9 Telugu': 'https://www.tv9telugu.com/feed',
            'TV5 News': 'https://www.tv5news.in/feed',
        },
        'Malayalam': {
            'Manorama Online': 'https://www.manoramaonline.com/content/mm/ml/news.rss.xml',
            'Mathrubhumi': 'https://www.mathrubhumi.com/rss/news-1.1129.xml',
        },
        'Kannada': {
             'Prajavani': 'https://www.prajavani.net/taxonomy/term/72/feed',
             'Udayavani': 'https://www.udayavani.com/feed'
        },
        'Tamil': {
            'Oneindia (Tamil)': 'https://tamil.oneindia.com/rss/tamil-news-fb.xml'
        }
    }
}


# --- Database Functions ---
def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    # Added a sub_category column for languages
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            link TEXT NOT NULL UNIQUE,
            publishedAt TEXT,
            sourceName TEXT,
            category TEXT,
            sub_category TEXT, 
            imageUrl TEXT,
            viewCount INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

# --- News Fetching Logic ---
def fetch_single_feed(source_name, feed_url, category, sub_category=None):
    try:
        feed = feedparser.parse(feed_url)
        articles = []
        for entry in feed.entries:
            image_url = None
            if 'media_content' in entry and entry.media_content:
                image_url = entry.media_content[0].get('url')
            elif 'links' in entry:
                for link in entry.links:
                    if link.get('rel') == 'enclosure' and 'image' in link.get('type', ''):
                        image_url = link.get('href')
                        break
            
            articles.append((
                entry.title,
                entry.link,
                entry.get('published', ''),
                source_name,
                category,
                sub_category,
                image_url
            ))
        return articles
    except Exception as e:
        print(f"Error fetching {source_name} ({feed_url}): {e}")
        return []

def fetch_and_store_news():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    new_articles_count = 0
    
    tasks = []
    with ThreadPoolExecutor(max_workers=15) as executor:
        for category, sources in NEWS_FEEDS.items():
            if category == 'Indian News': # Handle nested structure
                for language, lang_sources in sources.items():
                    for name, url in lang_sources.items():
                        tasks.append(executor.submit(fetch_single_feed, name, url, category, language))
            else: # Handle flat structure
                for name, url in sources.items():
                    tasks.append(executor.submit(fetch_single_feed, name, url, category))

        for future in tasks:
            try:
                articles = future.result()
                for article in articles:
                    try:
                        cursor.execute('''
                            INSERT INTO articles (title, link, publishedAt, sourceName, category, sub_category, imageUrl)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', article)
                        new_articles_count += 1
                    except sqlite3.IntegrityError:
                        pass # Skip duplicates
            except Exception as e:
                print(f"Error processing future result: {e}")

    conn.commit()
    conn.close()
    return new_articles_count

# --- API Endpoints ---
@app.route('/get-news', methods=['GET'])
def get_news():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM articles ORDER BY viewCount DESC, publishedAt DESC")
    articles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    random.shuffle(articles)
    return jsonify(articles)

@app.route('/fetch-news', methods=['POST'])
def trigger_fetch():
    try:
        count = fetch_and_store_news()
        return jsonify({"message": f"Successfully fetched and stored {count} new articles."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/track-view', methods=['POST'])
def track_view():
    data = request.get_json()
    article_id = data.get('articleId')
    if not article_id:
        return jsonify({"error": "articleId is required"}), 400
    
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("UPDATE articles SET viewCount = viewCount + 1 WHERE id = ?", (article_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Main Execution ---
if __name__ == '__main__':
    init_db()
    print("Database initialized (with sub_category support).")
    # You might need to delete your old news.db file for the new column to be added cleanly
    app.run(debug=True)

