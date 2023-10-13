import json
from pathlib import Path
from datetime import datetime

from src.application.exporatory_bot import ExploratoryBot
from src.infraestructure.llm.prompt_service import PromptService
from src.infraestructure.web.browser_service import BrowserService
from src.infraestructure.reporting.reporting_service import ReportingService

with open("./config.json", "r") as f:
    config = json.load(f)

sut_reqs = config["sut"]["requirements"]
sut_test_data = config["sut"]["test_data"]
output_dir = f'{config["result_dir"]}/{datetime.now().strftime("%Y%m%d-%H%M%S")}'

Path(output_dir).mkdir(parents=True, exist_ok=True)

llm = PromptService(config["llm"])
browser = BrowserService(config["sut"]["base_url"])
bot = ExploratoryBot(output_dir, llm, browser, config["retry_attempts"])

bot.execute_use_cases(sut_reqs, sut_test_data, 1)

reporting = ReportingService(output_dir)
reporting.generate_report_file()
