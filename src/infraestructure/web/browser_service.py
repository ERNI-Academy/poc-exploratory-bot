
from bs4 import BeautifulSoup, Comment
from playwright.sync_api import sync_playwright

from src.domain.actions import Interaction

class BrowserService:

    def __init__(self):
        self.playwright = sync_playwright().start()

    def start(self):
        self.browser = self.playwright.chromium.launch(headless=False)
        context = self.browser.new_context()
        self.page = context.new_page()
        #self.page.goto(url)

    def get_url(self):
        return self.page.url
    
    def get_content(self):
        return self.clean_html(self.page.content())

    def close(self):
        self.page.close()
        
    def stop(self):
        self.playwright.stop()

    def check_bool_attr(self, attributes, attribute):
        return attribute in attributes and (attributes[attribute] == True or attributes[attribute] == "true")

    def is_hidden(self, element):
        if element.attrs:
            return self.check_bool_attr(element.attrs, 'aria-hidden') or self.check_bool_attr(element.attrs, 'hidden')
        return False

    # Function to remove tags
    def clean_html(self, html):
        soup = BeautifulSoup(html, "html.parser")
        for data in soup(['style', 'script', 'head', 'noscript', 'br', 'svg']):
            data.decompose()

        for data in soup():
            if isinstance(data, Comment):
                data.extract()
            if self.is_hidden(data):
                data.decompose()

        return str(soup()[0])

    def perform_action(self, interaction:Interaction):
        if interaction.action == 'navigation':
            url = interaction.params if interaction.params != '' else interaction.locator
            self.page.goto(url)
        if interaction.action == 'click':
            self.page.click(interaction.locator, timeout=1000)
        if interaction.action == 'write':
            self.page.fill(interaction.locator, interaction.params, timeout=1000)
        if interaction.action == 'select':
            self.page.locator(interaction.locator).select_option(interaction.params)

    def get_screenshot(self, output_path):
        self.page.screenshot(path=output_path)
