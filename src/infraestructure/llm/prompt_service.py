import json
import re
from string import Template
import openai
from time import sleep


class PromptService:
    def __init__(self, config: json) -> None:
        self.use_case_template_path = (
            "./src/infraestructure/llm/prompts/0_test_case.txt"
        )
        self.application_context_template_path = (
            "./src/infraestructure/llm/prompts/1_application_context.txt"
        )
        self.refine_steps_template_path = (
            "./src/infraestructure/llm/prompts/2_refine_steps.txt"
        )
        self.refine_steps_attempt_template_path = (
            "./src/infraestructure/llm/prompts/2_refine_steps_retry.txt"
        )
        self.verification_template_path = (
            "./src/infraestructure/llm/prompts/3_verification.txt"
        )
        self.test_verification_template_path = (
            "./src/infraestructure/llm/prompts/4_test_verification.txt"
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

        self.messages[-1] = {"role": "user", "content": prompt}
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

    def understand_application_context(self, data) -> (str, str):
        print("[ExploratoryBot] Getting application context...")
        request = self.apply_template(self.application_context_template_path, data)
        response = self.send_to_QA(request)
        return request, response

    def refine_next_steps(self, data) -> (str, str):
        print("[ExploratoryBot] Refining next steps...")
        request = self.apply_template(self.refine_steps_template_path, data)
        response = self.send_to_QA(request)
        return request, response

    def refine_next_step_attempt(self, data) -> (str, str):
        print("[ExploratoryBot] Refining next steps retry...")
        request = self.apply_template(self.refine_steps_attempt_template_path, data)
        response = self.send_to_QA(request)
        return request, response

    def decide_success_of_step(self, data):
        print("[ExploratoryBot] Checking success of step...")
        request = self.apply_template(self.verification_template_path, data)
        response = self.send_to_QA(request, False)
        return request, response

    def decide_success_of_test(self, data):
        print("[ExploratoryBot] Checking success of test...")
        request = self.apply_template(self.test_verification_template_path, data)
        response = self.send_to_QA(request)
        return request, response

    def apply_template(self, template, data) -> str:
        data["tokens"] = self.response_tokens
        with open(template, "r") as f:
            src = Template(f.read())
            return src.substitute(data)
