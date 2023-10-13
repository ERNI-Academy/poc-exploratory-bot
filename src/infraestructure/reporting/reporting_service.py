import json
import os
from pathlib import Path
import re
import shutil
import warnings


class ReportingService:

    def __init__(self, results_dir):
        self.results_dir = results_dir
        self.report_template_full_path = os.path.join(Path(__file__).resolve().parent, "templates", "report_template.md")
        self.step_template_full_path = os.path.join(Path(__file__).resolve().parent, "templates", "step_template.md")
        self.step_rationale_template_full_path = os.path.join(Path(__file__).resolve().parent, "templates", "rationale_template.md")
        self.elements_reviewed_template_full_path = os.path.join(Path(__file__).resolve().parent, "templates", "elements_reviewed_template.md")
        self.interaction_attempt_template_full_path = os.path.join(Path(__file__).resolve().parent, "templates", "interaction_attempt_template.md")
        self.evidence_template_full_path = os.path.join(Path(__file__).resolve().parent, "templates", "evidence_template.md")
        self.output_full_path = os.path.join(self.results_dir, "report.md")

    def read_file_content(self, path):
        path = Path(path)
        return path.read_text()
    
    def get_file_content_as_json(self, path):
        with open(os.path.join(self.results_dir, path), 'r') as f:
            data = json.load(f)
            return data
    
    def write_file_content(self, path, content):
        path = Path(path)
        path.write_text(content)

    def append_to_file(self, path, content):
        with open(path, "a") as f:
                f.write(content)

    def get_attempt_file_list(self, step_index, base_pattern):
        pattern = re.compile(step_index + base_pattern)
        results_dir_files = os.listdir(self.results_dir)
        return list(filter(pattern.match, results_dir_files))

    def get_last_attempt_file(self, step_index, base_pattern):
        return self.get_attempt_file_list(step_index, base_pattern)[-1]
    
    def replace_step_content(self, step_index, action, expected, requirements, step_result):
        base_step = "| $index | $action | $expected | [$reqs] | $status |\n"
        step_result_color = "green" if step_result.upper() == "PASS" else "red"

        step_content = base_step.replace("$index", step_index)
        step_content = step_content.replace("$action", action)
        step_content = step_content.replace("$expected", expected)
        step_content = step_content.replace("$reqs", ', '.join(str(x) for x in requirements))
        step_content = step_content.replace("$status", f"<span style=\"color:{step_result_color}\">**{step_result.upper()}**</span>")
        return step_content
    
    def replace_interactions_content(self, interactions, step_index, attempt):
        interaction_template_content = self.read_file_content(self.interaction_attempt_template_full_path)
        interaction_content = ""

        for interaction in interactions:
            base_interaction = "| $attempt | $action_index | $action | $locator | $params | $screenshot |\n"
            interaction_content += base_interaction.replace("$attempt", str(attempt))
            action_index = str(interactions.index(interaction) + 1)
            interaction_content = interaction_content.replace("$action_index", action_index)
            interaction_content = interaction_content.replace("$action", interaction["action"].upper())
            interaction_content = interaction_content.replace("$locator", interaction["locator"])
            interaction_content = interaction_content.replace("$params", interaction["params"] if "params" in interaction.keys() else "--")
            screenshot_file_name = f"{step_index}_{attempt}_action_{action_index}.png"

            if (interaction["action"].upper() == "INSPECTION"):
                screenshot_path = "--"
            elif (os.path.isfile(os.path.join(self.results_dir, screenshot_file_name))):
                screenshot_path = f"[{screenshot_file_name}]({screenshot_file_name})"
            else:
                screenshot_path = "<span style=\"color:red\">Action error</span>"
            interaction_content = interaction_content.replace("$screenshot", screenshot_path)

        return interaction_template_content.replace("$interactions", interaction_content)
    
    def replace_verification_content(self, step_content, step_acceptance_criteria, step_result_explanation):
        step_template_text = self.read_file_content(self.step_template_full_path)
        step_template_text = step_template_text.replace("$step_output", step_content)
        step_template_text = step_template_text.replace("$step_acceptance_criteria", step_acceptance_criteria)
        step_template_text = step_template_text.replace("$step_result_explanation", step_result_explanation)
        return step_template_text
    
    def replace_step_rationale(self, rationale_type, step_explanation):
        template = self.read_file_content(self.step_rationale_template_full_path)
        template = template.replace("$rationale_type", rationale_type)
        template = template.replace("$step_explanation", step_explanation)
        return template
    
    def replace_elements_reviewed(self, elements_reviewed):
        elements_reviewed_text = ""
        for element_reviewed in elements_reviewed:
            template = self.read_file_content(self.elements_reviewed_template_full_path)
            elements_reviewed_text += template.replace("$index", str(elements_reviewed.index(element_reviewed) + 1))
            elements_reviewed_text = elements_reviewed_text.replace("$locator", element_reviewed["locator"])
            elements_reviewed_text = elements_reviewed_text.replace("$explanation", element_reviewed["explanation"])
        return elements_reviewed_text
    
    def replace_evidences(self, index, step_name, evidence_file):
        evidence_template_text = self.read_file_content(self.evidence_template_full_path)
        evidence_template_text = evidence_template_text.replace("$index", index)
        evidence_template_text = evidence_template_text.replace("$step_expected", step_name)
        evidence_template_text = evidence_template_text.replace("$evidence_file", evidence_file)
        return evidence_template_text


    def replace_use_case_data(self):
        data = self.get_file_content_as_json("0_use_cases_res.json")
        use_case = data["use_cases"][0]
        use_case_name = use_case["name"]
        self.steps = use_case["steps"]
        assumptions = use_case["assumptions"]        

        output_report_text = self.read_file_content(self.output_full_path)
        output_report_text = output_report_text.replace("$use_case_name", use_case_name)
        self.write_file_content(self.output_full_path, output_report_text)
        
        for step in self.steps:
            step_index = str(self.steps.index(step) + 1)

            try:
                verification_latest_attempt_file = self.get_last_attempt_file(step_index, r"_\d{1,2}_verification_res\.json")
                data = self.get_file_content_as_json(verification_latest_attempt_file)
                step_acceptance_criteria = data["acceptance_criteria"]
                step_result_explanation = data["explanation"]
                step_result = data["result"]
                step_satisfied = data["satisfied"]
                step_satisfied_explanation = step_satisfied["explanation"]
                step_satisfied_elements = step_satisfied["elements_reviewed"]
                step_not_satisfied = data["not_satisfied"]
                step_not_satisfied_explanation = step_not_satisfied["explanation"]
                step_not_satisfied_elements = step_not_satisfied["elements_reviewed"]

                action_attempt_file_list = self.get_attempt_file_list(step_index, r"_\d{1,2}_action_res\.json")
                data = self.get_file_content_as_json(action_attempt_file_list[0])
                interactions_content = self.replace_interactions_content(data["interactions"], step_index, 0)
                for attempt_file in action_attempt_file_list[1:]:
                    data = self.get_file_content_as_json(attempt_file)
                    interactions_content += self.replace_interactions_content(data["interactions"], step_index, action_attempt_file_list.index(attempt_file))        

                step_content = self.replace_step_content(step_index, step["action"], step["expected"], step["requirements"], step_result)

                step_template_text = self.replace_verification_content(
                    step_content,
                    step_acceptance_criteria,
                    step_result_explanation)
                
                
                step_template_text = step_template_text.replace("$interactions_output", interactions_content)

                if (step_result.upper() == "PASS"):
                    rationale_type = "Satisfied"
                    elements_reviewed = step_satisfied_elements                   
                    step_explanation = step_satisfied_explanation
                else:
                    rationale_type = "Not Satisfied"
                    elements_reviewed = step_not_satisfied_elements
                    step_explanation = step_not_satisfied_explanation

                step_result_rationale_text = self.replace_step_rationale(rationale_type, step_explanation)
                elements_reviewed_text = self.replace_elements_reviewed(elements_reviewed)
                step_result_rationale_text = step_result_rationale_text.replace("$elements_reviewed", elements_reviewed_text)


                step_template_text = step_template_text.replace("$step_result_rationale", step_result_rationale_text)

                evidence_latest_attemp_file = self.get_last_attempt_file(step_index, r"_\d{1,2}_verification_image\.png")
                evidence_text = self.replace_evidences(step_index, step["expected"], evidence_latest_attemp_file)

                step_template_text = step_template_text.replace("$evidence", evidence_text)
                self.append_to_file(self.output_full_path, step_template_text)
            
            except (FileNotFoundError, IndexError) as e:
                warnings.warn("There was an issue generating the report, it may contain invalid data.")
    

    def generate_report_file(self):
        shutil.copyfile(self.report_template_full_path, self.output_full_path)
        self.replace_use_case_data()

