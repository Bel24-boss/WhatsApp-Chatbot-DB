import json
from pathlib import Path
from typing import Any


class CommercialRules:
    """Business-owned product and suitability configuration.

    The default catalogue permits structured capture only. A recommendation is
    returned exclusively when the file is explicitly approved and a matching
    rule exists; this prevents a technical deployment from inventing advice.
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"approved": False, "products": [], "recommendation_rules": []}
        return loaded if isinstance(loaded, dict) else {"approved": False}

    @property
    def approved(self) -> bool:
        return self.data.get("approved") is True and bool(self.data.get("approval_reference"))

    @property
    def products(self) -> list[dict[str, Any]]:
        products = self.data.get("products")
        return [item for item in products if isinstance(item, dict)] if isinstance(products, list) else []

    def product(self, product_id: str) -> dict[str, Any] | None:
        return next((item for item in self.products if item.get("id") == product_id), None)

    def recommend(self, answers: dict[str, Any]) -> dict[str, Any] | None:
        if not self.approved:
            return None
        rules = self.data.get("recommendation_rules")
        if not isinstance(rules, list):
            return None
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            conditions = rule.get("when") or {}
            if not isinstance(conditions, dict) or not conditions:
                continue
            valid_conditions = [
                answers.get(key) in allowed
                for key, allowed in conditions.items()
                if isinstance(allowed, list) and allowed
            ]
            if len(valid_conditions) == len(conditions) and all(valid_conditions):
                product = self.product(str(rule.get("product_id") or ""))
                if product:
                    return product
        return None
