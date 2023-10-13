from bs4 import BeautifulSoup, Comment
from playwright.sync_api import sync_playwright, expect

from src.domain.actions import Interaction


class BrowserService:
    def __init__(self, url):
        self.playwright = sync_playwright().start()
        self.url = url

    def start(self):
        self.browser = self.playwright.chromium.launch(headless=False)
        context = self.browser.new_context(ignore_https_errors=True)
        self.page = context.new_page()
        self.page.goto(self.url)

    def get_url(self):
        return self.page.url

    def get_content(self):
        return self.clean_html(self.page.content())

    def close(self):
        self.page.close()

    def stop(self):
        self.playwright.stop()

    def check_bool_attr(self, attributes, attribute):
        return attribute in attributes and (
            attributes[attribute] == True or attributes[attribute] == "true"
        )

    def is_hidden(self, element):
        if element.attrs:
            return self.check_bool_attr(
                element.attrs, "aria-hidden"
            ) or self.check_bool_attr(element.attrs, "hidden")
        return False

    # Function to remove tags
    def clean_html(self, html):
        soup = BeautifulSoup(html, "html.parser")
        for data in soup(["style", "script", "head", "noscript", "br", "svg"]):
            data.decompose()

        for data in soup():
            if isinstance(data, Comment):
                data.extract()
            if self.is_hidden(data):
                data.decompose()

        return str(soup()[0])

    def perform_action(self, interaction: Interaction):
        if interaction.action == "navigation":
            url = (
                interaction.params if interaction.params != "" else interaction.locator
            )
            self.page.goto(url)
        self.assert_element_exists(interaction.locator)
        if interaction.action == "click":
            self.page.click(interaction.locator, timeout=1000)
        if interaction.action == "write":
            self.page.fill(interaction.locator, interaction.params, timeout=1000)
        if interaction.action == "select":
            self.page.locator(interaction.locator).select_option(interaction.params)

    def assert_element_exists(self, xpath):
        if not self.page.locator(xpath).is_visible():
            raise ValueError(
                f"It was expected element {xpath} to be present but it is not present in the DOM"
            )

    def assert_element_not_exists(self, xpath):
        if self.page.locator(xpath).is_visible():
            raise ValueError(
                f"It was expected element {xpath} to not be present but it is present in the DOM"
            )

    def get_screenshot(self, output_path):
        self.page.screenshot(path=output_path)
