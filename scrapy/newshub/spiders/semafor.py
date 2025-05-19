from fake_useragent import UserAgent
from bs4 import BeautifulSoup

from scrapy import Spider, Request
from ..items import NewsItem
from ..utils.html_cleaner import clean_html

class SemaforSpider(Spider):
    name = "semafor_spider"
    allowed_domains = ["semafor.com"]
    custom_settings = {
        "ROBOTSTXT_OBEY": False
    }
    ua = UserAgent()

    def __init__(self, url: str = None, _job: str = None, *args, **kwargs):
        # Scrapyd передаёт здесь _job=<jobid>
        super().__init__(*args, **kwargs)
        self.start_urls = [url] if url else []
        self._job = _job     # сохраняем job_id для пайплайнов

    def start_requests(self):
        for url in self.start_urls:
            yield Request(
                url=url,
                headers={'User-Agent': self.ua.random},
                callback=self.parse
            )

    def parse(self, response):
        item = NewsItem()
        item['url'] = response.url
        item['title'] = (
            response.xpath('//main//h1[contains(@class, "suppress-rss")]/text()')
                    .get(default='')
                    .strip()
        )

        html_block = response.xpath(
            '//main//div[contains(@class, "article-content")]'
        ).get(default='')
        soup = BeautifulSoup(html_block, 'html.parser')
        for tag in soup.find_all(attrs={"data-testid": "ad-body"}):
            tag.decompose()
        for tag in soup.find_all(
            class_=lambda c: c and c.startswith("styles_indexMenu_")
        ):
            tag.decompose()

        # Вот правильный вызов clean_html
        cleaned_html = clean_html(
            str(soup),
            ['p', 'h2', 'h3', 'h4', 'i', 'b']
        )
        # и если нужно, простая замена тегов
        cleaned_html = cleaned_html.replace('<h2>', '<h3>').replace('</h2>', '</h3>')
        item['job_id'] = self._job
        item['html'] = cleaned_html
        item['text'] = clean_html(cleaned_html)

        yield item
