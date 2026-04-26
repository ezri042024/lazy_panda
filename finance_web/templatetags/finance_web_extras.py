from django import template

register = template.Library()


@register.filter
def account_logo(account):
    name = f"{account.name or ''} {account.institution_name or ''}".lower()

    logo_map = {
        "bpi": "finance_web/logos/bpi.png",
        "gcash": "finance_web/logos/gcash.png",
        "unionbank": "finance_web/logos/unionbank.jpg",
        "union bank": "finance_web/logos/unionbank.png",
        "bdo": "finance_web/logos/bdo.png",
        "metrobank": "finance_web/logos/metrobank.png",
        "maya": "finance_web/logos/maya.png",
        "paymaya": "finance_web/logos/maya.png",
    }

    for keyword, logo_path in logo_map.items():
        if keyword in name:
            return logo_path

    return ""


@register.filter
def account_default_icon(account):
    account_type = (account.account_type or "").lower()

    icon_map = {
        "cash": "bi-cash-stack",
        "bank": "bi-bank",
        "ewallet": "bi-phone",
        "investment": "bi-graph-up-arrow",
        "credit_card": "bi-credit-card",
        "loan": "bi-file-earmark-text",
    }

    return icon_map.get(account_type, "bi-wallet2")