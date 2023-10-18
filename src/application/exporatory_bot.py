import json
import os
import codecs
from datetime import datetime
from dataclasses import asdict
from typing import Dict
from dacite import from_dict
from src.domain.actions import Interaction, Interactions
from time import sleep

from src.domain.use_cases import UseCase, UseCaseData, UseCases
from src.domain.verifications import Verifications
from src.infraestructure.llm.prompt_service import PromptService
from src.infraestructure.web.browser_service import BrowserService


class ExploratoryBot:
    use_case_sample: str = "./src/domain/samples/use_case.json"
    action_catalog_sample: str = "./src/domain/samples/action_catalog.json"
    verification_sample: str = "./src/domain/samples/verification.json"
    action_sample: str = "./src/domain/samples/action.json"

    def __init__(
        self,
        out_dir: str,
        prompt_service: PromptService,
        browser_service: BrowserService,
        attempts: int = 1,
    ):
        self.out_dir = out_dir
        self.base_dir = os.path.dirname(out_dir)
        self.prompt_service = prompt_service
        self.browser_service = browser_service
        self.attempts = attempts

    def execute_use_cases(self, sut_reqs, sut_test_data, n_cases=1):
        executed_scenarios = []
        covered_reqs = []
        while n_cases > 0:
            try:
                test_case = self.generate_test_case(sut_reqs)
                self.execute_test_case(sut_reqs, sut_test_data, test_case)
                print(test_case)
            except Exception as e:
                print(e)
            finally:
                n_cases -= 1

    def execute_test_case(self, reqs_path, test_data_path, test_case):
        self.browser_service.start()
        step_number = 0
        test_case["test_case"]["steps"] = []
        application_context = self.get_application_context(step_number)
        is_test_running = True

        while is_test_running:
            step_number += 1
            test_case = self.refine_test_steps(
                reqs_path, test_data_path, test_case, application_context, step_number
            )
            test_case = self.execute_step(test_case, step_number, test_data_path)
            application_context = self.get_application_context(step_number)
            test_case = self.verify_step_execution(
                test_case, step_number, application_context
            )
            test_case, is_test_running = self.verify_test_execution(
                test_case, step_number
            )

            self.write_file(
                f"{self.out_dir}/__{step_number}_test_case.json", json.dumps(test_case)
            )
        self.browser_service.stop()
        return test_case

    def verify_test_execution(self, test_case, step_number):
        test_context = {
            "name": test_case["test_case"]["name"],
            "description": test_case["test_case"]["description"],
            "verification_scope": test_case["test_case"]["verification_scope"],
        }

        exploratory_stages = "\n".join(
            [
                f"{i*4}. {step['Arrange']}\n{(i*3)+1}. {step['Act']}\n{(i*3)+2}. {step['Assert']}\n{(i*3)+3}. {step['summary']}"
                for i, step in enumerate(test_case["test_case"]["steps"])
            ]
        )
        verification_questions = [
            f"  - Is the {verification} already met during the exploratory stages?"
            for verification in test_case["test_case"]["atomic_verifications"]
        ]
        verification_data = {
            "test_context": json.dumps(test_context),
            "exploratory_stages": exploratory_stages,
            "atomic_verifications": "\n".join(verification_questions),
        }

        request, response = self.prompt_service.decide_success_of_test(
            verification_data
        )
        self.write_file(
            f"{self.out_dir}/{step_number}_test_verification_req.txt",
            request,
        )
        self.write_file(
            f"{self.out_dir}/{step_number}_test_verification_res.json",
            response,
        )
        verified = json.loads(response)
        if verified["result"] != "unkown":
            test_case["test_case"]["result"] = verified["result"]
            test_case["test_case"]["verification_status"] = verified[
                "result_explanation"
            ]

        return test_case, verified["need_more_steps"]

    def verify_step_execution(self, test_case, step_number, application_context):
        verification_data = {
            "test_case": json.dumps(test_case),
            "step_number": step_number,
            "application_context": application_context,
        }

        request, response = self.prompt_service.decide_success_of_step(
            verification_data
        )
        self.write_file(
            f"{self.out_dir}/{step_number}_verification_req.txt",
            request,
        )
        self.write_file(
            f"{self.out_dir}/{step_number}_verification_res.json",
            response,
        )
        verification = json.loads(response)
        if verification["step_met"]:
            test_case["test_case"]["steps"][step_number - 1]["result"] = "pass"
            test_case["test_case"]["steps"][step_number - 1]["summary"] = verification[
                "match_explanation"
            ]
            test_case["test_case"]["user_journey"].pop(0)
        else:
            test_case["test_case"]["steps"][step_number - 1]["result"] = "fail"
            test_case["test_case"]["steps"][step_number - 1]["summary"] = verification[
                "match_explanation"
            ]
        self.browser_service.get_screenshot(
            f"{self.out_dir}/{step_number}_verification.png"
        )
        return test_case

    def check_elements_missing(self, test_case, step_number):
        interactions = []
        elements_missing = []
        for raw_action in test_case["test_case"]["steps"][step_number - 1]["actions"]:
            try:
                self.browser_service.assert_element_exists(raw_action["locator"])
                params = raw_action["params"] if "params" in raw_action else ""
                interactions.append(
                    Interaction(raw_action["action"], raw_action["locator"], params)
                )
            except:
                elements_missing.append(raw_action["locator"])

        return interactions, elements_missing

    def execute_step(self, test_case, step_number, test_data_path):
        interactions, elements_missing = self.check_elements_missing(
            test_case, step_number
        )
        attempt = 1
        while len(elements_missing) > 0 and attempt < self.attempts:
            test_case = self.refine_step_attempt(
                test_case, step_number, test_data_path, attempt
            )
            interactions, elements_missing = self.check_elements_missing(
                test_case, step_number
            )
            attempt += 1

        if len(elements_missing) > 0:
            test_case["test_case"]["steps"][step_number - 1]["status"] = "unkown"
            test_case["test_case"]["steps"][step_number - 1][
                "Then"
            ] = "Is not possible to determine the next step of the test case. No more steps are needed. Test case ends here."

        action = 0
        for interaction in interactions:
            try:
                sleep(1)
                self.browser_service.perform_action(interaction)
                test_case["test_case"]["steps"][step_number - 1]["actions"][action][
                    "status"
                ] = "pass"
            except Exception:
                test_case["test_case"]["steps"][step_number - 1]["actions"][action][
                    "status"
                ] = "fail"
            finally:
                self.browser_service.get_screenshot(
                    f"{self.out_dir}/{step_number}_action_{action}.png"
                )
                action += 1
        return test_case

    def refine_step_attempt(self, test_case, step_number, test_data_path, attempt):
        prompt_path = f"{self.out_dir}/{step_number}_refine_{attempt}_req.txt"
        response_path = f"{self.out_dir}/{step_number}_refine_{attempt}_res.json"

        response_template = test_case["test_case"]["steps"][step_number - 1]
        response_template["actions"] = [
            {
                "action": "from the available actions",
                "locator": "XPath of the element to perform the action",
                "params": "any param needed to perform the action",
            }
        ]

        data = {
            "url": self.browser_service.get_url(),
            "DOM": self.browser_service.get_content(),
            "available_actions": self.read_file(self.action_catalog_sample),
            "test_data": self.read_file(test_data_path),
            "test_case": json.dumps(test_case),
            "response_template": json.dumps(response_template),
        }

        request, response = self.prompt_service.refine_next_step_attempt(data)
        self.write_file(prompt_path, request)
        self.write_file(response_path, response)
        new_step = json.loads(response)
        test_case["test_case"]["steps"][step_number - 1] = new_step
        return test_case

    def refine_test_steps(
        self, reqs_path, test_data_path, test_case, application_context, step_number
    ):
        prompt_path = f"{self.out_dir}/{step_number}_refine_req.txt"
        response_path = f"{self.out_dir}/{step_number}_refine_res.json"

        response_template = {
            "step_number": step_number,
            "Arrange": application_context["application_context"],
            "Act": "FILL THE BLANK",
            "actions": [
                {
                    "action": "from the available actions",
                    "locator": "XPath of the element to perform the action",
                    "params": "any param needed to perform the action",
                }
            ],
            "Assert": test_case["test_case"]["user_journey"][0]["step"],
            "requirements": ["FILL THE BLANK"],
        }

        data = {
            "requirements": self.read_file(reqs_path),
            "application_context": json.dumps(application_context),
            "available_actions": self.read_file(self.action_catalog_sample),
            "actions_template": self.read_file(self.action_sample),
            "test_data": self.read_file(test_data_path),
            "test_case": json.dumps(test_case),
            "response_template": json.dumps(response_template),
        }

        request, response = self.prompt_service.refine_next_steps(data)
        self.write_file(prompt_path, request)
        self.write_file(response_path, response)
        new_step = json.loads(response)
        test_case["test_case"]["steps"].append(new_step)
        return test_case

    def get_application_context(self, step):
        prompt_path = f"{self.out_dir}/{step}_context_req.txt"
        response_path = f"{self.out_dir}/{step}_context_res.json"

        data = {
            "url": self.browser_service.get_url(),
            "DOM": self.browser_service.get_content(),
            "elements": json.dumps(self.browser_service.get_relevant_elements()),
        }

        request, response = self.prompt_service.understand_application_context(data)
        self.write_file(prompt_path, request)
        self.write_file(response_path, response)
        return json.loads(response)

    def generate_test_case(self, req_path):
        prompt_path = f"{self.out_dir}/0_test_case_req.txt"
        response_path = f"{self.out_dir}/0_test_case_res.json"

        data = {
            "requirements": self.read_file(req_path),
        }

        request, response = self.prompt_service.decide_new_use_case(data)
        self.write_file(prompt_path, request)
        self.write_file(response_path, response)
        return json.loads(response)

    def read_file(self, file_path: str) -> str:
        with codecs.open(file_path, "r", "utf-8") as f:
            return f.read()

    def write_file(self, file_path: str, content: str):
        with codecs.open(file_path, "w", "utf-8") as f:
            print(f" File generated: ", file_path)
            f.write(content)
