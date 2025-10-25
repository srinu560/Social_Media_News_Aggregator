import os
import boto3
import feedparser
from concurrent.futures import ThreadPoolExecutor

# --- DynamoDB Configuration ---
# The table name is passed as an environment variable to the Lambda function
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'NewsArticles')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

# --- RSS Feed Configuration (Complete List) ---
NEWS_FEEDS = {
    'Technology': {
        'TechCrunch': 'http://feeds.feedburner.com/TechCrunch/',
        'Wired': 'https://www.wired.com/feed/rss',
        'The Verge': 'https://www.theverge.com/rss/index.xml'
    },
    'Business': {
        'Reuters Business': 'http://feeds.reuters.com/reuters/businessNews',
        'Wall Street Journal': 'https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml',
        'Forbes': 'https://www.forbes.com/business/feed/'
    },
    'Entertainment': {
        'Variety': 'https://variety.com/feed/',
        'The Hollywood Reporter': 'https://www.hollywoodreporter.com/feed/',
        'TMZ': 'https://www.tmz.com/rss.xml'
    },
    'Crime': {
        'NYT Crime': 'https://www.nytimes.com/svc/collections/v1/publish/www.nytimes.com/section/us/crime/rss.xml'
    },
    'World News': {
        'BBC World': 'http://feeds.bbci.co.uk/news/world/rss.xml',
        'Reuters World': 'http://feeds.reuters.com/Reuters/worldNews',
        'Associated Press': 'https://apnews.com/hub/world-news/rss'
    },
    'Indian News': {
        'English': { 'Times of India': 'https://timesofindia.indiatimes.com/rssfeedstopstories.cms', 'The Hindu': 'https://www.thehindu.com/news/national/feeder/default.rss', 'NDTV': 'https://feeds.feedburner.com/ndtvnews-latest', },
        'Hindi': { 'BBC Hindi': 'https://feeds.bbci.co.uk/hindi/rss.xml', 'Dainik Jagran': 'https://www.jagran.com/rss/news/national.xml', },
        'Telugu': { 'Sakshi': 'https://www.sakshi.com/rss', 'TV9 Telugu': 'https://www.tv9telugu.com/feed', 'TV5 News': 'https://www.tv5news.in/feed', },
        'Malayalam': { 'Manorama Online': 'https://www.manoramaonline.com/content/mm/ml/news.rss.xml', 'Mathrubhumi': 'https://www.mathrubhumi.com/rss/news-1.1129.xml', },
        'Kannada': { 'Prajavani': 'https://www.prajavani.net/taxonomy/term/72/feed', 'Udayavani': 'https://www.udayavani.com/feed' },
        'Tamil': { 'Oneindia (Tamil)': 'https://tamil.oneindia.com/rss/tamil-news-fb.xml' }
    }
}

def fetch_single_feed(source_name, feed_url, category, sub_category=None):
    """Parses a single RSS feed and returns a list of articles."""
    try:
        feed = feedparser.parse(feed_url)
        articles = []
        for entry in feed.entries:
            # Simple check to ensure basic fields exist
            if not all(hasattr(entry, attr) for attr in ['title', 'link']):
                continue

            image_url = None
            if 'media_content' in entry and entry.media_content:
                image_url = entry.media_content[0].get('url')
            elif 'links' in entry:
                for link in entry.links:
                    if link.get('rel') == 'enclosure' and 'image' in link.get('type', ''):
                        image_url = link.get('href')
                        break
            
            # The article link is the primary key (Partition Key) in DynamoDB
            articles.append({
                'link': entry.link,
                'title': entry.title,
                'publishedAt': entry.get('published', 'N/A'),
                'sourceName': source_name,
                'category': category,
                'sub_category': sub_category or 'N/A',
                'imageUrl': image_url or 'N/A',
                'viewCount': 0
            })
        return articles
    except Exception as e:
        print(f"Error fetching {source_name} ({feed_url}): {e}")
        return []

def lambda_handler(event, context):
    """
    Main Lambda function handler.
    Fetches news from all sources and stores them in DynamoDB.
    """
    print("Starting news fetch process...")
    new_articles_count = 0
    
    tasks = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        for category, sources in NEWS_FEEDS.items():
            if category == 'Indian News': # Handle nested structure
                for language, lang_sources in sources.items():
                    for name, url in lang_sources.items():
                        tasks.append(executor.submit(fetch_single_feed, name, url, category, language))
            else: # Handle flat structure
                for name, url in sources.items():
                    tasks.append(executor.submit(fetch_single_feed, name, url, category))

    with table.batch_writer() as batch:
        for future in tasks:
            try:
                articles = future.result()
                for article in articles:
                    # batch_writer handles duplicates and overwrites, which is fine.
                    # This ensures we don't need a separate check for existence.
                    batch.put_item(Item=article)
                    new_articles_count += 1
            except Exception as e:
                print(f"Error processing future result: {e}")

    print(f"Fetch process completed. Processed {new_articles_count} articles.")
    return {
        'statusCode': 200,
        'body': f'Successfully processed {new_articles_count} articles.'
    }


