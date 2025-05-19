from fake_useragent import UserAgent
from bs4 import BeautifulSoup
from scrapy import Spider, Request

from ..items import NewsItem
from ..utils.html_cleaner import clean_html


class ArabianBusinessSpider(Spider):
    name = "arabianbusiness_spider"
    allowed_domains = ["arabianbusiness.com"]
    custom_settings = {
        # чтобы игнорировать robots.txt
        "ROBOTSTXT_OBEY": False,
    }

    def __init__(self, url: str = None, _job: str = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [url] if url else []
        self._job = _job
        self.ua = UserAgent()

    def start_requests(self):
        for url in self.start_urls:
            yield Request(
                url=url,
                headers={"User-Agent": self.ua.random},
                callback=self.parse
            )

    def parse(self, response):
        item = NewsItem()
        item["url"] = response.url

        # 1) Заголовок статьи
        title = response.xpath('//h1/text()').get()
        if not title:
            title = response.xpath('//article//h1/text()').get()
        item["title"] = title.strip() if title else ""

        # 2) Содержимое — все <p> внутри <article>, либо резервно внутри .article-body
        paragraphs = response.xpath('//article//p').getall()
        if not paragraphs:
            paragraphs = response.xpath(
                '//div[contains(@class,"article-body")]//p'
            ).getall()
        html_block = "".join(paragraphs)

        # 3) Чистка через BeautifulSoup + clean_html
        soup = BeautifulSoup(html_block, "html.parser")
        # удаляем блоки «Follow us» и прочий шум
        for tag in soup.find_all("p"):
            if "Follow us" in tag.get_text():
                tag.decompose()

        cleaned_html = clean_html(
            str(soup),
            ['p', 'h2', 'h3', 'h4', 'i', 'b'],
            {'h2': 'h3'}
        )
        item["html"] = cleaned_html
        # plain-text для перевода/саммари
        item["text"] = clean_html(cleaned_html)

        # 4) job_id для пайплайнов
        item["job_id"] = self._job

        yield item

