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


class InteractionException(Exception):
    interaction: Interaction = None

    def __init__(self, interaction, original_exception, *args: object) -> None:
        super().__init__(*args)
        self.interaction = interaction
        self.original_exception = original_exception


class VerificationException(Exception):
    pass


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
                use_cases = self.generate_use_cases_from_reqs(
                    sut_reqs, executed_scenarios, covered_reqs
                )
                use_case = use_cases.use_cases[0]
                verification = self.execute_use_case(use_case, sut_test_data)
                print(verification)

                covered_reqs.extend(
                    [req for step in use_case.steps for req in step.requirements]
                )
                executed_scenarios.append(use_case.name)
            except Exception as e:
                print(e)
            finally:
                n_cases -= 1

    def generate_use_cases_from_reqs(
        self,
        req_path,
        executed_scenarios,
        covered_requirements,
        prompt_name="0_use_cases_req.txt",
        response_name="0_use_cases_res.json",
    ):
        prompt_path = f"{self.out_dir}/{prompt_name}"
        response_path = f"{self.out_dir}/{response_name}"

        reqs = self.read_file(req_path)
        sample = json.loads(self.read_file(self.use_case_sample))
        scenarios = str(executed_scenarios)
        cov_reqs = str(covered_requirements)
        data = asdict(UseCaseData(reqs, json.dumps(sample), scenarios, cov_reqs))

        request, response = self.prompt_service.decide_new_use_case(data)
        self.write_file(prompt_path, request)
        self.write_file(response_path, response)
        use_cases = from_dict(UseCases, json.loads(response))
        return use_cases

    def execute_use_case(self, use_case: UseCase, test_data_path: str):
        verifications = []
        action_catalog = self.read_file(self.action_catalog_sample)
        test_data = self.read_file(test_data_path)

        template_action = self.read_file(self.action_sample)
        template_verification = self.read_file(self.verification_sample)


        steps = json.dumps([{"step_number": i+1, "action": step.action, "acceptance": step.expected} for (i,step) in enumerate(use_case.steps)])

        action_data = {
            "test_data": test_data,
            "action_template": template_action,
            "use_case_name": use_case.name,
            "use_case_steps": str(steps),
            "action_catalog": action_catalog,
            "url": "$url",
            "DOM": "$DOM",
            "step": "$step",
        }

        verification_data = {
            "url": "$url",
            "DOM": "$DOM",
            "test_data": test_data,
            "verification_template": str(template_verification),
            "use_case_name": use_case.name,
            "use_case_steps": steps,
            "step": "$step",
        }

        step = 1
        self.browser_service.start()

        for use_step in use_case.steps:
            attempt = 0
            verification = None
            name = f"{step}"
            path = f"{self.out_dir}/{step}_{attempt}_action"
            interactions = self.resolve_use_case_step_actions(
                name, action_data, self.out_dir
            )
            while attempt <= self.attempts:
                try:
                    self.execute_interactions(interactions, path)
                    sleep(1)
                    verification = self.verify_use_case_step_expected(
                        step, verification_data, self.out_dir, attempt
                    )
                    if verification.result == "fail":
                        raise VerificationException
                    break

                except InteractionException as e:
                    attempt += 1
                    path = f"{self.out_dir}/{step}_{attempt}_action"
                    interactions = self.resolve_use_case_attempt_actions(
                        f"{step}_{attempt}", e, self.out_dir
                    )
                except VerificationException as e:
                    attempt += 1
                    interactions = self.resolve_use_case_step_actions(
                        name, action_data, self.out_dir, attempt
                    )

            if verification is None:
                verification = self.verify_use_case_step_expected(
                    step, verification_data, self.out_dir, attempt
                )

            verifications.append(verification)

            if verification.result == "fail":
                break

            step += 1

        self.browser_service.close()
        return verifications

    def execute_interactions(self, interactions: Interactions, path):
        action = 1
        for interaction in interactions.interactions:
            try:
                self.browser_service.perform_action(interaction)
            except Exception as e:
                raise InteractionException(interaction, e)
            finally:
                self.browser_service.get_screenshot(f"{path}_{action}.png")
                action += 1

    def resolve_use_case_attempt_actions(
        self, attempt, exception: InteractionException, folder: str
    ):
        prompt_path = f"{folder}/{attempt}_attempt_req.txt"
        response_path = f"{folder}/{attempt}_attempt_res.json"
        data = {
            "url": self.browser_service.get_url(),
            "DOM": self.browser_service.get_content(),
            "action": str(exception.interaction.__dict__),
            "error": exception.original_exception.message,
            "template_action": self.read_file(self.action_sample),
        }
        request, response = self.prompt_service.decide_actions_from_attempt(data)

        self.write_file(prompt_path, request)
        self.write_file(response_path, response)
        return from_dict(Interactions, json.loads(response))

    def verify_use_case_step_expected(
        self, step, verification_data: Dict, folder: str, attempt: int = 0
    ):
        prompt_path = f"{folder}/{step}_{attempt}_verification_req.txt"
        response_path = f"{folder}/{step}_{attempt}_verification_res.json"

        verification_data.update(
            {
                "url": self.browser_service.get_url(),
                "DOM": self.browser_service.get_content(),
                "step": step,
            }
        )

        request, response = self.prompt_service.decide_success_of_step(
            verification_data
        )
        self.write_file(prompt_path, request)
        self.write_file(response_path, response)
        verifications = from_dict(Verifications, json.loads(response))
        self.browser_service.get_screenshot(
            f"{folder}/{step}_{attempt}_verification_image.png"
        )
        return verifications

    def resolve_use_case_step_actions(
        self, step, action_data: Dict, folder: str, attempt: int = 0
    ):
        prompt_path = f"{folder}/{step}_{attempt}_action_req.txt"
        response_path = f"{folder}/{step}_{attempt}_action_res.json"
        action_data.update(
            {
                "url": self.browser_service.get_url(),
                "DOM": self.browser_service.get_content(),
                "step": step,
            }
        )
        request, response = self.prompt_service.decide_actions_from_step(action_data)

        self.write_file(prompt_path, request)
        self.write_file(response_path, response)
        return from_dict(Interactions, json.loads(response))

    def read_file(self, file_path: str) -> str:
        with codecs.open(file_path, "r", "utf-8") as f:
            return f.read()

    def write_file(self, file_path: str, content: str):
        with codecs.open(file_path, "w", "utf-8") as f:
            f.write(content)
