import os
import json
import boto3
from boto3.dynamodb.conditions import Key
from decimal import Decimal

# --- DynamoDB Configuration ---
TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'NewsArticles')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

class DecimalEncoder(json.JSONEncoder):
    """Helper class to convert a DynamoDB item to JSON."""
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o)
        return super(DecimalEncoder, self).default(o)

def create_response(status_code, body):
    """Creates a standard API Gateway response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
        },
        'body': json.dumps(body, cls=DecimalEncoder)
    }

def lambda_handler(event, context):
    """
    Handles API Gateway requests.
    Routes to different functions based on the HTTP method and path.
    """
    http_method = event.get('httpMethod')
    path = event.get('path')

    if http_method == 'GET' and path == '/news':
        return get_news()
    elif http_method == 'POST' and path == '/track-view':
        return track_view(event)
    else:
        return create_response(404, {'error': 'Not Found'})

def get_news():
    """Scans the DynamoDB table and returns all articles."""
    try:
        # Note: A Scan operation reads every item in a table.
        # For large tables, this can be slow and expensive.
        # For this project's scale, it is acceptable.
        response = table.scan()
        articles = response.get('Items', [])
        
        # Sort by view count and then by published date (if available)
        # This is done in code because DynamoDB Scan doesn't guarantee order.
        articles.sort(key=lambda x: x.get('viewCount', 0), reverse=True)
        
        return create_response(200, articles)
    except Exception as e:
        print(f"Error getting news: {e}")
        return create_response(500, {'error': 'Could not retrieve news articles.'})

def track_view(event):
    """Increments the view count for a given article link."""
    try:
        body = json.loads(event.get('body', '{}'))
        article_link = body.get('articleLink')

        if not article_link:
            return create_response(400, {'error': 'articleLink is required.'})

        table.update_item(
            Key={'link': article_link},
            UpdateExpression='SET viewCount = viewCount + :val',
            ExpressionAttributeValues={':val': 1}
        )
        return create_response(200, {'status': 'success'})
    except Exception as e:
        print(f"Error tracking view: {e}")
        return create_response(500, {'error': 'Could not update view count.'})
