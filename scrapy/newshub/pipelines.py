# scrapy/newshub/pipelines.py

from itemadapter import ItemAdapter
import lxml.html
import requests
from deep_translator import GoogleTranslator
from telegraph import Telegraph
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from scrapy.exceptions import DropItem
from .models import Item, create_tables


class TranslationPipeline:
    def __init__(self):
        self.translator = GoogleTranslator(source='auto', target='ru')

    def process_item(self, item, spider):
        doc = lxml.html.fromstring(item['text'])
        def translate_element(el):
            if el.text and el.text.strip():
                el.text = self.translator.translate(el.text)
            for child in el:
                translate_element(child)
                if child.tail and child.tail.strip():
                    child.tail = self.translator.translate(child.tail)
        translate_element(doc)
        item['text'] = lxml.html.tostring(doc, encoding='unicode')
        return item


class TelegraphPipeline:
    def __init__(self, telegraph_token):
        self.telegraph = Telegraph(telegraph_token)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get('TELEGRAPH_TOKEN'))

    def process_item(self, item, spider):
        try:
            html = f"{item['html']}<p>Источник: <a href=\"{item['url']}\">{item['url']}</a></p>"
            resp = self.telegraph.create_page(title=item['title'], html_content=html)
            item['telegraph_url'] = "https://telegra.ph/" + resp['path']
            spider.logger.info(f"Publish Telegraph successful: {item['telegraph_url']}")
        except Exception as e:
            spider.logger.error(f"Error publish to Telegraph: {e}")
            raise DropItem(f"Error publish to Telegraph: {item['title']}")
        return item


class DatabasePipeline:
    def __init__(self, db_url):
        self.engine = create_engine(db_url)
        create_tables(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get('DATABASE_URL'))

    def open_spider(self, spider):
        self.session = self.Session()

    def close_spider(self, spider):
        self.session.close()

    def process_item(self, item, spider):
        if not all([item.get('url'), item.get('job_id'), item.get('title'),
                    item.get('text'), item.get('html')]):
            raise DropItem(f"Missing required fields in {item}")

        db_item = self.session.query(Item).filter_by(url=item['url']).first()
        if db_item:
            item['id'] = db_item.id
            db_item.job_id         = item['job_id']
            db_item.title          = item['title']
            db_item.text           = item['text']
            db_item.html           = item['html']
            db_item.telegraph_url  = item.get('telegraph_url')
            db_item.tags           = item.get('tags')
            db_item.status         = 'DONE'
            self.session.add(db_item)
            self.session.commit()
        else:
            spider.logger.warning(f"Item with url '{item['url']}' not found in the database.")
        return item


class WebhookPipeline:
    def __init__(self):
        # поправили URL: нужно именно /api/v1/scrapyd/webhook/{item_id}
        self.webhook_url = 'http://api:8000/api/v1/scrapyd/webhook/'

    def process_item(self, item, spider):
        if not item.get('id'):
            spider.logger.error(f"Webhook skipped, no ID in item {item!r}")
            return item
        try:
            resp = requests.get(f'{self.webhook_url}{item["id"]}', timeout=5)
            resp.raise_for_status()
            spider.logger.info(f"Webhook OK: GET {self.webhook_url}{item['id']}")
        except Exception as e:
            spider.logger.error(f"Webhook Error: {e}")
        return item
