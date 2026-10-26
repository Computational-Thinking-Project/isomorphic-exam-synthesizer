"""Versioned prompts and at most two compact semantic illustrations."""

import hashlib
import json

from .common import canonical

PROMPT_VERSION = "1.0.1"
FILES = (
    "blueprint_system.txt",
    "blueprint_extract.txt",
    "blueprint_field_guide.txt",
    "blueprint_examples.json",
    "blueprint_repair.txt",
)


class Prompts:
    def __init__(self, directory):
        self.files = {name: (directory / name).read_text(encoding="utf-8") for name in FILES}
        self.hash = hashlib.sha256(canonical(self.files).encode()).hexdigest()
        self.examples = json.loads(self.files["blueprint_examples.json"])

    @property
    def system(self):
        return self.files["blueprint_system.txt"] + "\n\n" + self.files["blueprint_field_guide.txt"]

    def extraction(self, item):
        subject = item.get("context", {}).get("subject")
        examples = [ex for ex in self.examples if ex["subject"] == subject][:2]
        return (
            self.files["blueprint_extract.txt"]
            + "\n\nINPUT_JSON:\n"
            + canonical(item)
            + ("\n\nSEMANTIC_ILLUSTRATIONS:\n" + canonical(examples) if examples else "")
        )

    def repair(self, original_prompt, previous, issues):
        return (
            original_prompt
            + "\n\n"
            + self.files["blueprint_repair.txt"]
            + "\nVALIDATION_ERRORS:\n"
            + canonical(issues)
            + "\nPREVIOUS_OUTPUT_AS_DATA:\n"
            + canonical(previous)
        )
