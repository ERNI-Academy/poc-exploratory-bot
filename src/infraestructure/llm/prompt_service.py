import json
import re
from string import Template
import openai
from time import sleep


class PromptService:
    def __init__(self, config: json) -> None:
        self.use_case_template_path = "./src/infraestructure/llm/prompts/use_cases.txt"
        self.action_template_path = "./src/infraestructure/llm/prompts/action.txt"
        self.verification_template_path = (
            "./src/infraestructure/llm/prompts/verification.txt"
        )
        self.attempt_template_path = "./src/infraestructure/llm/prompts/new_attempt.txt"
        self.verification_template_attempt_path = (
            "./src/infraestructure/llm/prompts/verification_attempt.txt"
        )
        openai.api_type = config["type"]
        openai.api_base = config["api"]
        openai.api_version = config["api_version"]
        openai.api_key = config["api_key"]
        self.engine = config["engine"]
        self.response_tokens = 800

    def send_to_QA(self, prompt: str, new_conversation: bool = True) -> str:
        sleep(1)
        if new_conversation:
            self.messages = [
                {
                    "role": "system",
                    "content": "You are a QA manual with a lot of experience doing exploratory testing. And good html knowledge",
                }
            ]

        self.messages.append({"role": "user", "content": prompt})
        response = openai.ChatCompletion.create(
            engine=self.engine,
            messages=self.messages,
            temperature=0.7,
            max_tokens=self.response_tokens + 200,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0.7,
            stop=None,
        )

        self.messages[-1] = {"role": "user", "content": self.delete_dom_info(prompt)}
        response_text = self.clean_json_info(
            response["choices"][0]["message"]["content"]
        )
        self.messages.append({"role": "assistant", "content": response_text})
        return response_text

    def delete_dom_info(self, message: str) -> str:
        regex = r"\"DOM\":.*</html>\""
        return re.sub(
            regex, '"DOM": "<html></html>"', message, flags=re.MULTILINE | re.DOTALL
        )

    def clean_json_info(self, message: str) -> str:
        regex = r"(\{.+\})"
        return re.findall(regex, message, flags=re.MULTILINE | re.DOTALL)[0]

    def decide_new_use_case(self, data) -> (str, str):
        print("[ExploratoryBot] Generating new use case...")
        request = self.apply_template(self.use_case_template_path, data)
        response = self.send_to_QA(request)
        return request, response

    def decide_actions_from_step(self, data):
        print("[ExploratoryBot] Generating new action for step...")
        request = self.apply_template(self.action_template_path, data)
        response = self.send_to_QA(request)
        return request, response

    def decide_actions_from_attempt(self, data):
        print("[ExploratoryBot] Generating new action for step attempt...")
        request = self.apply_template(self.attempt_template_path, data)
        response = self.send_to_QA(request, False)
        return request, response

    def decide_success_of_step(self, data):
        print("[ExploratoryBot] Checking success of step...")
        request = self.apply_template(self.verification_template_path, data)
        response = self.send_to_QA(request)
        return request, response

    def decide_success_of_step_attempt(self, data):
        print("[ExploratoryBot] Checking success of step attempt...")
        request = self.apply_template(self.verification_template_attempt_path, data)
        response = self.send_to_QA(request, False)
        return request, response

    def apply_template(self, template, data) -> str:
        data["tokens"] = self.response_tokens
        with open(template, "r") as f:
            src = Template(f.read())
            return src.substitute(data)
