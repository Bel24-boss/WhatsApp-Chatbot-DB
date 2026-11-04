from typing import Any


MAIN_MENU = (
    "*Welcome to Fidelity Life Assurance Group*\n"
    "Protecting what matters most.\n\n"
    "1. Self Service\n"
    "2. Ask a Question\n"
    "3. Urgent Insurance Assistance\n"
    "4. Speak to an Agent"
)


MAIN_MENU_V11 = (
    "Welcome to Fidelity Life Assurance Group 🕊️\n"
    "*Protecting what matters most.*\n\n"
    "How can we help you secure your future today?\n\n"
    "Reply with a number to choose an option:\n\n"
    "1. 💼 Explore Insurance Products\n"
    "2. 📝 Get a Quote / Apply\n"
    "3. 🔎 Track My Application\n"
    "4. 💳 Premium Payments\n"
    "5. 📄 Policy & Cover Services\n"
    "6. 📞 Adviser & Contact Details"
)


SELF_SERVICE_MENU = (
    "*Self Service*\n\n"
    "1. Fidelity Life Assurance\n"
    "2. Employee Benefits\n"
    "3. Fidelity Funeral Services\n"
    "4. Fidelity Life Medical Aid Society (FLIMAS)\n"
    "5. Financial Services & Loans\n"
    "6. Wealth Management\n"
    "7. Actuarial Services\n"
    "8. Register / Link My Accounts\n"
    "9. Agent / Contact Us\n"
    "10. Needs & Quote Guidance\n\n"
    "Type *Back*, *Agent*, or *Cancel* at any time."
)


MENUS: dict[str, dict[str, Any]] = {
    "life_menu": {
        "title": "Fidelity Life Assurance",
        "lines": [
            "1. Explore Life Assurance",
            "2. View Products",
            "3. Get a Quote",
            "4. Apply for Cover",
            "5. Existing Policy",
            "6. Make a Payment",
            "7. Claims",
            "8. Documents",
            "9. FAQs",
            "10. Main Menu",
        ],
        "choices": {
            "1": "1.0", "2": "life_products_menu", "3": "commercial_product",
            "4": "life_apply_start", "5": "policy_menu", "6": "payment_identity_notice",
            "7": "claims_menu", "8": "life_documents", "9": "ask_question", "10": "main_menu",
        },
    },
    "life_products_menu": {
        "title": "Life Assurance Products",
        "lines": [
            "1. Vaka Yako Property Investment Plan",
            "2. Endowment & Savings Plans",
            "3. Retirement & Pensions",
            "4. Back to Life Assurance",
            "5. Main Menu",
        ],
        "choices": {"1": "1.1", "2": "1.2", "3": "1.3", "4": "life_menu", "5": "main_menu"},
    },
    "funeral_menu": {
        "title": "Fidelity Funeral Services",
        "lines": [
            "1. Beloved Funeral Plans",
            "2. Funeral Flexi Combo",
            "3. Immediate Bereavement Assistance",
            "4. Main Menu",
        ],
        "choices": {"1": "2.1", "2": "2.2", "3": "2.3", "4": "main_menu"},
    },
    "flimas_menu": {
        "title": "Fidelity Life Medical Aid Society (FLIMAS)",
        "lines": [
            "1. Individual & Family Health Packages",
            "2. Corporate Self-Managed Funds",
            "3. FLIMAS Member Self-Service",
            "4. Main Menu",
        ],
        "choices": {"1": "3.1", "2": "3.2", "3": "flimas_self_service", "4": "main_menu"},
    },
    "flimas_self_service": {
        "title": "FLIMAS Member Self-Service",
        "lines": [
            "1. Check Account Balance",
            "2. View Medical Card Acceptance Network",
            "3. Download FLIMAS App",
            "4. Back to FLIMAS",
            "5. Main Menu",
        ],
        "choices": {
            "1": "3.3.1",
            "2": "3.3.2",
            "3": "app_platform",
            "4": "flimas_menu",
            "5": "main_menu",
        },
    },
    "agent_menu": {
        "title": "Adviser & Contact Details",
        "lines": [
            "1. Request an Adviser",
            "2. View Contact Details",
            "3. Main Menu",
        ],
        "choices": {"1": "escalation_category", "2": "4.2", "3": "main_menu"},
    },
}


SERVICES: dict[str, dict[str, Any]] = {
    "1.0": {
        "title": "Explore Life Assurance",
        "parent": "life_menu",
        "team": "Life Assurance",
        "summary": (
            "Explore Fidelity Life Assurance products and assisted services. Product-specific benefits, "
            "premiums, eligibility, exclusions and policy terms must come from approved Fidelity records."
        ),
        "options": "1. View Products\n2. Get Guidance\n3. Back\n4. Main Menu",
        "actions": {"1": "life_products_menu", "2": "enquiry", "3": "back", "4": "main_menu"},
        "fields": [("customer_need", "What would you like Life Assurance to help you with?")],
    },
    "1.1": {
        "title": "Vaka Yako Property Investment Plan",
        "parent": "life_menu",
        "team": "Life Assurance",
        "summary": (
            "Vaka Yako combines life assurance with a property-investment pathway. "
            "Current contributions, cover, land locations, availability and terms must come from "
            "Fidelity's approved active product records."
        ),
        "options": "1. Check Land Locations\n2. Request a Quote\n3. Back\n4. Main Menu",
        "actions": {"1": "1.1.1", "2": "enquiry", "3": "back", "4": "main_menu"},
        "fields": [("preferred_location", "Which town or province are you interested in?")],
    },
    "1.1.1": {
        "title": "Vaka Yako Land Locations",
        "parent": "service:1.1",
        "team": "Life / Property Team",
        "summary": (
            "Current land inventory has not been approved for publication in this chatbot. "
            "Fidelity staff can confirm locations and availability without promising a reservation."
        ),
        "options": "1. Request Location Assistance\n2. Back\n3. Main Menu",
        "actions": {"1": "enquiry", "2": "back", "3": "main_menu"},
        "fields": [("preferred_location", "Which town or province are you interested in?")],
    },
    "1.2": {
        "title": "Endowment & Savings Plans",
        "parent": "life_menu",
        "team": "Life Assurance",
        "summary": (
            "These plans combine life protection with long-term savings or maturity benefits. "
            "An adviser must confirm current plan-specific guarantees, terms and exclusions."
        ),
        "options": "1. Request an Adviser Callback\n2. Back\n3. Main Menu",
        "actions": {"1": "enquiry", "2": "back", "3": "main_menu"},
        "fields": [("savings_purpose", "What is your main savings goal?")],
    },
    "1.3": {
        "title": "Retirement & Pensions",
        "parent": "life_menu",
        "team": "Pensions Team",
        "summary": "Fidelity provides individual retirement and corporate employee-benefit options.",
        "options": (
            "1. Individual Retirement Enquiry\n2. Corporate Employee Benefits Enquiry\n"
            "3. Back\n4. Main Menu"
        ),
        "actions": {"1": "enquiry:individual", "2": "enquiry:corporate", "3": "back", "4": "main_menu"},
        "fields": [("retirement_objective", "Briefly describe your retirement objective.")],
        "corporate_fields": [("company_name", "What is the company name?")],
    },
    "2.1": {
        "title": "Beloved Funeral Plans",
        "parent": "funeral_menu",
        "team": "Funeral Sales",
        "summary": (
            "Fidelity offers four Beloved plan options. Current premiums, casket descriptions, "
            "bus inclusions and terms require an approved active product record before publication."
        ),
        "options": "1. Enquire About a Plan\n2. Back\n3. Main Menu",
        "actions": {"1": "enquiry", "2": "back", "3": "main_menu"},
        "fields": [("plan_interest", "Which plan are you interested in, or should an adviser help you choose?")],
    },
    "2.2": {
        "title": "Funeral Flexi Combo",
        "parent": "funeral_menu",
        "team": "Funeral Sales",
        "summary": (
            "Flexi Combo combines funeral-service and cash-benefit options. Fidelity staff must "
            "confirm current price, benefits, eligibility and waiting periods."
        ),
        "options": "1. Request a Callback\n2. Back\n3. Main Menu",
        "actions": {"1": "enquiry", "2": "back", "3": "main_menu"},
        "fields": [],
    },
    "2.3": {
        "title": "Immediate Bereavement Assistance",
        "parent": "funeral_menu",
        "team": "Funeral Operations",
        "summary": "urgent",
        "options": "1. Request Urgent Staff Assistance\n2. Back\n3. Main Menu",
        "actions": {"1": "enquiry", "2": "back", "3": "main_menu"},
        "fields": [("current_location", "What town or location are you currently in?")],
        "priority": "urgent",
    },
    "3.1": {
        "title": "Individual & Family Health Packages",
        "parent": "flimas_menu",
        "team": "FLIMAS Membership",
        "summary": (
            "FLIMAS offers seven package options. Current rates, billing period, benefit limits, "
            "age definitions and network rules must be approved before publication."
        ),
        "options": "1. Enquire About a Package\n2. Back\n3. Main Menu",
        "actions": {"1": "enquiry", "2": "back", "3": "main_menu"},
        "fields": [("package_interest", "Which package interests you, or should a consultant help you choose?")],
    },
    "3.2": {
        "title": "Corporate Self-Managed Funds",
        "parent": "flimas_menu",
        "team": "FLIMAS Corporate Team",
        "summary": (
            "Fidelity can discuss tailored corporate medical-fund administration. A corporate "
            "consultant must confirm the current service and reinsurance arrangements."
        ),
        "options": "1. Request Corporate Consultation\n2. Back\n3. Main Menu",
        "actions": {"1": "enquiry", "2": "back", "3": "main_menu"},
        "fields": [("company_name", "What is the company name?")],
    },
    "5.1": {
        "title": "Financial Services & Loans",
        "parent": "self_service_menu",
        "team": "Financial Services & Loans",
        "summary": "A Fidelity representative can provide approved information about currently available financial services and loan enquiries.",
        "options": "1. Request Assistance\n2. Back\n3. Main Menu",
        "actions": {"1": "enquiry", "2": "back", "3": "main_menu"},
        "fields": [("enquiry", "Briefly describe the financial service or loan assistance you need.")],
    },
    "6.1": {
        "title": "Wealth Management",
        "parent": "self_service_menu",
        "team": "Wealth Management",
        "summary": "A Fidelity representative can provide approved information about available wealth-management services.",
        "options": "1. Request Assistance\n2. Back\n3. Main Menu",
        "actions": {"1": "enquiry", "2": "back", "3": "main_menu"},
        "fields": [("enquiry", "Briefly describe the wealth-management assistance you need.")],
    },
    "7.1": {
        "title": "Actuarial Services",
        "parent": "self_service_menu",
        "team": "Actuarial Services",
        "summary": "A Fidelity representative can provide approved information about available actuarial services.",
        "options": "1. Request Assistance\n2. Back\n3. Main Menu",
        "actions": {"1": "enquiry", "2": "back", "3": "main_menu"},
        "fields": [("enquiry", "Briefly describe the actuarial-service assistance you need.")],
    },
}


DIRECT_ROUTE_STATES = {
    "1": "self_service_menu",
    "2": "ask_question",
    "3": "urgent_assistance",
    "4": "escalation_category",
}


DIRECT_ROUTE_STATES_V11 = {
    "1": "product_catalog",
    "2": "application_product_catalog",
    "3": "application_tracking_reference",
    "4": "payments_menu",
    "5": "policy_cover_menu",
    "6": "agent_menu",
}


CATALOGUE_ROUTE_ALIASES = {
    "m0": "main_menu",
    "m1": "product_catalog",
    "m2": "product_catalog",
    "m3": "application_product_catalog",
    "m4": "application_tracking_reference",
    "m5": "payments_menu",
    "m6": "policy_cover_menu",
    "m7": "funeral_menu",
    "m7.3": "urgent_assistance",
    "m8": "agent_menu",
    "m8.1": "agent_menu",
    "m9": "flimas_menu",
    "m9.3": "flimas_self_service",
}


LEGACY_SERVICES_MENU = {
    "title": "Other Fidelity Services",
    "lines": [
        "1. Fidelity Funeral Services",
        "2. Fidelity Life Medical Aid Society (FLIMAS)",
        "3. Other Fidelity Services",
        "4. Explore Insurance Products",
        "5. Main Menu",
    ],
    "choices": {
        "1": "funeral_menu",
        "2": "flimas_menu",
        "3": "self_service_menu",
        "4": "product_catalog",
        "5": "main_menu",
    },
}

MENUS["legacy_services_menu"] = LEGACY_SERVICES_MENU


SELF_SERVICE_ROUTE_STATES = {
    "1": "life_menu",
    "2": "1.3",
    "3": "funeral_menu",
    "4": "flimas_menu",
    "5": "5.1",
    "6": "6.1",
    "7": "7.1",
    "8": "onboarding_service",
    "9": "agent_menu",
    "10": "commercial_product",
}


ONBOARDING_SERVICES = {
    "1": ("life", "Life Assurance", "FLA"),
    "2": ("employee_benefits", "Employee Benefits", "FLA"),
    "3": ("funeral", "Funeral Services", "FFS"),
    "4": ("medical_aid", "Medical Aid", "FLIMAS"),
    "5": ("financial_services", "Financial Services and Loans", "FLFS"),
    "6": ("wealth_management", "Wealth Management", "owner_pending"),
    "7": ("actuarial_services", "Actuarial Services", "ZAC"),
}


ESCALATION_CATEGORIES = {
    "1": ("life", "Life Assurance"),
    "2": ("funeral", "Funeral Services"),
    "3": ("flimas", "FLIMAS"),
    "4": ("complaint", "Customer Care / Complaints"),
    "5": ("general", "General Customer Care"),
}
