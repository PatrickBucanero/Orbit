import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

_api_url = os.getenv("SMM_API_URL", "").strip()
_api_key = os.getenv("SMM_API_KEY", "").strip()


def configure(smm_api_url: str, smm_api_key: str) -> None:
    global _api_url, _api_key
    _api_url = smm_api_url.strip().rstrip("/")
    _api_key = smm_api_key.strip()


def _request(action: str, **data: Any) -> Any:
    if not _api_url or not _api_key:
        raise RuntimeError("Configure SMM_API_URL e SMM_API_KEY antes de usar o fornecedor.")
    payload = {"key": _api_key, "action": action, **data}
    try:
        response = requests.post(_api_url, data=payload, timeout=30)
    except requests.RequestException as exc:
        raise RuntimeError(f"Falha de conexão com o fornecedor SMM: {exc}") from exc
    response.raise_for_status()
    result = response.json()
    if isinstance(result, dict) and result.get("error"):
        raise RuntimeError(str(result["error"]))
    return result


def buscar_servicos() -> dict[str, Any]:
    try:
        result = _request("services")
    except RuntimeError as exc:
        return {"sucesso": False, "servicos": [], "erro": str(exc)}
    if not isinstance(result, list):
        return {"sucesso": False, "servicos": [], "erro": "A API SMM retornou uma lista de serviços inválida."}
    services = []
    for item in result:
        if not isinstance(item, dict):
            continue
        text = f"{item.get('name', '')} {item.get('category', '')}".lower()
        platform = next((name for name in ("Instagram", "TikTok", "YouTube", "Kwai", "Facebook") if name.lower() in text), "Outro")
        services.append({
            "service": str(item.get("service", "")),
            "name": str(item.get("name", "")),
            "category": str(item.get("category", "")),
            "rate": float(item.get("rate", 0) or 0),
            "min": int(item.get("min", 0) or 0),
            "max": int(item.get("max", 0) or 0),
            "type": str(item.get("type", "default")),
            "plataforma": platform,
        })
    return {"sucesso": True, "servicos": services, "mensagem": f"{len(services)} serviços sincronizados."}


def enviar_pedido_smm(
    link: str,
    quantidade: int,
    service_id: str,
    comments: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"service": service_id, "link": link, "quantity": quantidade}
    if comments:
        payload["comments"] = comments
    result = _request("add", **payload)
    if not isinstance(result, dict) or not result.get("order"):
        raise RuntimeError("A API SMM não retornou um identificador de pedido.")
    return result


def consultar_status(order_id: str) -> dict[str, Any]:
    result = _request("status", order=order_id)
    if not isinstance(result, dict):
        raise RuntimeError("A API SMM retornou um status inválido.")
    return result


def consultar_saldo() -> dict[str, Any]:
    result = _request("balance")
    if not isinstance(result, dict) or "balance" not in result:
        raise RuntimeError("A API SMM não retornou o saldo.")
    return result
