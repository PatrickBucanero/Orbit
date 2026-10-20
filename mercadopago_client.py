import os
from typing import Any

import mercadopago
from dotenv import load_dotenv

load_dotenv()

_access_token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "").strip()
_sdk: mercadopago.SDK | None = mercadopago.SDK(_access_token) if _access_token else None


def configure(access_token: str) -> None:
    global _access_token, _sdk
    _access_token = access_token.strip()
    _sdk = mercadopago.SDK(_access_token) if _access_token else None


def _client() -> mercadopago.SDK:
    if _sdk is None:
        raise RuntimeError("Configure o access token do Mercado Pago antes de criar pagamentos.")
    return _sdk


def gerar_pix(order_id: int, amount: float, description: str, payer_email: str) -> dict[str, Any]:
    payment_data = {
        "transaction_amount": round(amount, 2),
        "description": description,
        "payment_method_id": "pix",
        "payer": {"email": payer_email},
        "external_reference": str(order_id),
    }
    result = _client().payment().create(payment_data)
    if result.get("status", 500) >= 400:
        raise RuntimeError(f"Mercado Pago recusou o pagamento: {result.get('response', result)}")
    response = result.get("response", {})
    transaction_data = response.get("point_of_interaction", {}).get("transaction_data", {})
    return {
        "id": str(response["id"]),
        "payment_id": str(response["id"]),
        "status": response.get("status", "pending"),
        "qr_code_base64": transaction_data.get("qr_code_base64"),
        "qr_code": transaction_data.get("qr_code"),
        "date_of_expiration": response.get("date_of_expiration"),
    }


def verificar_pagamento(payment_id: str) -> dict[str, Any]:
    result = _client().payment().get(payment_id)
    if result.get("status", 500) >= 400:
        raise RuntimeError(f"Não foi possível consultar o pagamento: {result.get('response', result)}")
    return result.get("response", {})


def testar_conexao() -> dict[str, Any]:
    result = _client().payment().search({"limit": 1})
    if result.get("status", 500) >= 400:
        raise RuntimeError(f"Mercado Pago recusou o teste de conexão: {result.get('response', result)}")
    return {"connected": True}


gerar_cobranca_pix = gerar_pix
consultar_pagamento = verificar_pagamento
