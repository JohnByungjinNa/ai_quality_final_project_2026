import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


class EventValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("event contract validation failed")


class EventContract:
    def __init__(self, schema_path):
        schema_path = Path(schema_path)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.schema_path = schema_path
        self.validator = Draft202012Validator(schema, format_checker=FormatChecker())

    def validate(self, event):
        errors = sorted(self.validator.iter_errors(event), key=lambda item: list(item.absolute_path))
        if errors:
            formatted = []
            for error in errors[:20]:
                path = ".".join(str(part) for part in error.absolute_path) or "$"
                formatted.append(
                    {
                        "path": path,
                        "code": error.validator,
                        "message": "event field failed the contract rule",
                    }
                )
            raise EventValidationError(formatted)
        return event
