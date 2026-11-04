from typing import Optional

from app.catalog import MAIN_MENU_V11


class FidelityLifeBot:
    """Stateless compatibility helper for simple menu previews and unit tests."""

    MENU_TEXT = MAIN_MENU_V11

    def get_welcome_message(self, user_name: Optional[str] = None) -> str:
        greeting = f"Hello {user_name}." if user_name else "Hello."
        return f"{greeting} Welcome to Fidelity Life Assurance.\n\n{self.MENU_TEXT}"

    def process_message(self, text: str, user_name: Optional[str] = None) -> str:
        cleaned = (text or "").strip().lower()
        if cleaned in {"hi", "hello", "hey", "start", "menu", "main menu", "help"}:
            return self.get_welcome_message(user_name)
        selections = {
            "1": "Explore Insurance Products selected. Please continue in the WhatsApp conversation.",
            "2": "Apply for Insurance selected. Please continue in the WhatsApp conversation.",
            "3": "Track an Application selected. Please continue in the WhatsApp conversation.",
            "4": "Payments selected. Please continue in the WhatsApp conversation.",
            "5": "Policy and Cover Assistance selected. Please continue in the WhatsApp conversation.",
            "6": "Agent and contact services selected. Please continue in the WhatsApp conversation.",
        }
        return selections.get(cleaned, f"That is not a valid selection.\n\n{self.MENU_TEXT}")




