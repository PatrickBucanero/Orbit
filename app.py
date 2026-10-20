import csv
import io
import os
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import desc, func, inspect, or_, select, text
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine, get_db
from mercadopago_client import gerar_pix, testar_conexao, verificar_pagamento
from models import Configuracao, Order
from smm_client import buscar_servicos, consultar_saldo, enviar_pedido_smm, configure as configure_smm
from mercadopago_client import configure as configure_mercadopago

Base.metadata.create_all(bind=engine)
with engine.begin() as connection:
    existing_columns = {column["name"] for column in inspect(engine).get_columns("orders")}
    for column, definition in {
        "plataforma": "VARCHAR(40) NOT NULL DEFAULT 'Instagram'",
        "tipo_servico": "VARCHAR(60) NOT NULL DEFAULT 'seguidores'",
        "comentarios": "TEXT",
    }.items():
        if column not in existing_columns:
            connection.execute(text(f"ALTER TABLE orders ADD COLUMN {column} {definition}"))

startup_db = SessionLocal()
try:
    configuration = startup_db.get(Configuracao, 1)
    if configuration:
        configure_smm(configuration.smm_api_url, configuration.smm_api_key)
        configure_mercadopago(configuration.mercadopago_access_token)
finally:
    startup_db.close()

app = FastAPI(title="Orbit SMM Console", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")


class CreateOrderRequest(BaseModel):
    link: str = Field(min_length=5, max_length=500)
    plataforma: str = Field(default="Instagram", min_length=2, max_length=40)
    tipo_servico: str = Field(default="seguidores", min_length=2, max_length=60)
    service_id: str | None = None
    quantity: int | None = Field(default=None, ge=1, le=1_000_000)
    comentarios: str | None = Field(default=None, max_length=10_000)
    payer_email: EmailStr

    @field_validator("link")
    @classmethod
    def clean_link(cls, value: str) -> str:
        return value.strip()


class ConfigRequest(BaseModel):
    smm_api_url: str = Field(min_length=1, max_length=500)
    smm_api_key: str = Field(min_length=1)
    mercadopago_access_token: str = Field(min_length=1)
    margem_lucro_padrao_porcentagem: float = Field(ge=0, le=10_000)


def get_configuration(db: Session) -> Configuracao:
    configuration = db.get(Configuracao, 1)
    if configuration is None:
        configuration = Configuracao(id=1, margem_lucro_padrao_porcentagem=150.0)
        db.add(configuration)
        db.commit()
        db.refresh(configuration)
    return configuration


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:4]}••••{value[-4:]}"


def platform_from_category(category: str, name: str) -> str:
    value = f"{category} {name}".lower()
    for platform in ("instagram", "tiktok", "youtube", "kwai"):
        if platform in value:
            return platform.title()
    return "Outro"


def normalize_catalog_service(item: dict, margin_percentage: float) -> dict:
    rate = float(item.get("rate", item.get("rate_fornecedor", 0)) or 0)
    return {
        "service_id": str(item.get("service", item.get("service_id", ""))),
        "name": str(item.get("name", "")),
        "category": str(item.get("category", "")),
        "platform": item.get("plataforma") or platform_from_category(str(item.get("category", "")), str(item.get("name", ""))),
        "rate_fornecedor": rate,
        "preco_venda": round(rate * (1 + margin_percentage / 100), 2),
        "min": int(item.get("min", 0) or 0),
        "max": int(item.get("max", 0) or 0),
        "type": item.get("type", "default"),
    }


def provider_service_result() -> dict:
    result = buscar_servicos()
    if not result.get("sucesso"):
        raise HTTPException(status_code=502, detail=result.get("erro", "Não foi possível carregar o catálogo SMM."))
    return result

def serialize_order(order: Order) -> dict:
    return {
        "id": order.id,
        "link": order.link,
        "plataforma": order.plataforma,
        "tipo_servico": order.tipo_servico,
        "comentarios": order.comentarios,
        "service_id": order.service_id,
        "service_name": order.service_name,
        "quantity": order.quantity,
        "provider_cost": round(order.provider_cost, 2),
        "customer_price": round(order.customer_price, 2),
        "profit": round(order.customer_price - order.provider_cost, 2),
        "status": order.status,
        "external_payment_id": order.external_payment_id,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
    }


@app.get("/")
def home() -> FileResponse:
    return FileResponse("static/index.html")


@app.get("/api/servicos")
def services(db: Session = Depends(get_db)) -> list[dict]:
    configuration = get_configuration(db)
    result = provider_service_result()
    return [normalize_catalog_service(item, configuration.margem_lucro_padrao_porcentagem) for item in result["servicos"]]


@app.get("/api/catalogo")
def catalog(db: Session = Depends(get_db)) -> dict:
    configuration = get_configuration(db)
    result = buscar_servicos()
    if not result.get("sucesso"):
        return {"sucesso": False, "erro": result.get("erro", "Não foi possível carregar o catálogo SMM.")}
    services = [normalize_catalog_service(item, configuration.margem_lucro_padrao_porcentagem) for item in result["servicos"]]
    return {"sucesso": True, "servicos": services, "mensagem": result.get("mensagem", f"{len(services)} serviços sincronizados.")}


@app.get("/api/config")
def read_config(db: Session = Depends(get_db)) -> dict:
    configuration = get_configuration(db)
    return {
        "smm_api_url": configuration.smm_api_url,
        "smm_api_key": mask_secret(configuration.smm_api_key),
        "mercadopago_access_token": mask_secret(configuration.mercadopago_access_token),
        "margem_lucro_padrao_porcentagem": configuration.margem_lucro_padrao_porcentagem,
    }


@app.post("/api/config")
def save_config(payload: ConfigRequest, db: Session = Depends(get_db)) -> dict:
    configuration = get_configuration(db)
    configuration.smm_api_url = payload.smm_api_url.strip().rstrip("/")
    configuration.smm_api_key = payload.smm_api_key.strip()
    configuration.mercadopago_access_token = payload.mercadopago_access_token.strip()
    configuration.margem_lucro_padrao_porcentagem = payload.margem_lucro_padrao_porcentagem
    db.commit()
    configure_smm(configuration.smm_api_url, configuration.smm_api_key)
    configure_mercadopago(configuration.mercadopago_access_token)
    return read_config(db)


@app.get("/api/smm/saldo")
def provider_balance() -> dict:
    try:
        return consultar_saldo()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Não foi possível consultar o saldo SMM: {exc}") from exc


@app.get("/api/mercadopago/testar")
def mercado_pago_connection() -> dict:
    try:
        return testar_conexao()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Não foi possível conectar ao Mercado Pago: {exc}") from exc


@app.get("/api/analytics")
def analytics(db: Session = Depends(get_db)) -> dict:
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=6)
    thirty_days_ago = now - timedelta(days=29)
    paid_statuses = ["paid", "processing", "completed", "approved"]
    recent = db.scalars(select(Order).where(Order.status.in_(paid_statuses), Order.created_at >= thirty_days_ago)).all()
    paid = db.scalars(select(Order).where(Order.status.in_(paid_statuses))).all()
    daily = {}
    for offset in range(30):
        day = (thirty_days_ago + timedelta(days=offset)).date().isoformat()
        daily[day] = {"revenue": 0.0, "profit": 0.0}
    for order in recent:
        day = order.created_at.date().isoformat()
        if day in daily:
            daily[day]["revenue"] += order.customer_price
            daily[day]["profit"] += order.customer_price - order.provider_cost
    platform_counts: dict[str, int] = {}
    for order in paid:
        platform_counts[order.plataforma] = platform_counts.get(order.plataforma, 0) + 1
    total_orders = db.scalar(select(func.count(Order.id))) or 0
    approved_count = len(paid)
    return {
        "revenue_7_days": round(sum(item.customer_price for item in recent if item.created_at >= seven_days_ago), 2),
        "revenue_30_days": round(sum(item.customer_price for item in recent), 2),
        "net_profit": round(sum(item.customer_price - item.provider_cost for item in paid), 2),
        "conversion_rate": round((approved_count / total_orders * 100) if total_orders else 0, 2),
        "platforms": [{"platform": key, "sales": value, "percentage": round(value / approved_count * 100, 2) if approved_count else 0} for key, value in platform_counts.items()],
        "daily": [{"date": key, "revenue": round(value["revenue"], 2), "profit": round(value["profit"], 2)} for key, value in daily.items()],
    }


@app.post("/api/pedidos/criar")
def create_order(payload: CreateOrderRequest, db: Session = Depends(get_db)) -> dict:
    platform_key = payload.plataforma.strip().lower()
    service_type = payload.tipo_servico.strip().lower()
    type_aliases = {
        "seguidores / inscritos": "seguidores",
        "curtidas / likes": "curtidas",
        "visualizações / views": "visualizacoes",
        "comentários personalizados": "comentarios",
    }
    service_type = type_aliases.get(service_type, service_type)
    allowed_platforms = {"instagram", "tiktok", "youtube", "kwai"}
    if platform_key not in allowed_platforms:
        raise HTTPException(status_code=400, detail="Plataforma não suportada.")
    if service_type not in {"seguidores", "inscritos", "curtidas", "visualizacoes", "comentarios"}:
        raise HTTPException(status_code=400, detail="Tipo de serviço não suportado.")
    if service_type in {"seguidores", "inscritos"}:
        service_type = "inscritos" if platform_key == "youtube" else "seguidores"
    normalized_comments = None
    if service_type == "comentarios":
        normalized_comments = "\n".join(line.strip() for line in (payload.comentarios or "").splitlines() if line.strip())
        quantity = len(normalized_comments.splitlines()) if normalized_comments else 0
        if not quantity:
            raise HTTPException(status_code=400, detail="Informe pelo menos um comentário, um por linha.")
    else:
        quantity = payload.quantity or 0
        if quantity < 10:
            raise HTTPException(status_code=400, detail="A quantidade mínima é 10.")
    service_id = payload.service_id or f"{platform_key}-{service_type}"
    configuration = get_configuration(db)
    provider_services = provider_service_result()["servicos"]
    provider_service = next((item for item in provider_services if str(item.get("service", item.get("service_id", ""))) == service_id), None)
    if provider_service is None:
        raise HTTPException(status_code=400, detail="Serviço real não encontrado no catálogo do fornecedor.")
    service_name = str(provider_service.get("name", service_id))
    provider_rate = float(provider_service.get("rate", provider_service.get("rate_fornecedor", 0)) or 0)
    provider_min = int(provider_service.get("min", 0) or 0)
    provider_max = int(provider_service.get("max", 0) or 0)
    if provider_min and quantity < provider_min or provider_max and quantity > provider_max:
        raise HTTPException(status_code=400, detail=f"A quantidade deve estar entre {provider_min} e {provider_max}.")
    provider_cost = provider_rate * quantity / 1000
    customer_price = round(provider_cost * (1 + configuration.margem_lucro_padrao_porcentagem / 100), 2)
    order = Order(
        link=payload.link,
        plataforma=payload.plataforma.strip(),
        tipo_servico=service_type,
        comentarios=normalized_comments,
        service_id=service_id,
        service_name=service_name,
        quantity=quantity,
        provider_cost=round(provider_cost, 2),
        customer_price=customer_price,
        status="pending",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    try:
        payment = gerar_pix(order.id, customer_price, f"{service_name} - {quantity} unidades", str(payload.payer_email))
    except Exception as exc:
        db.delete(order)
        db.commit()
        raise HTTPException(status_code=502, detail=f"Não foi possível gerar o PIX: {exc}") from exc
    order.external_payment_id = payment["id"]
    order.pix_copy_paste = payment.get("qr_code")
    order.pix_qr_code = payment.get("qr_code_base64")
    db.commit()
    return {"order": serialize_order(order), "payment": payment}


@app.get("/api/pedidos")
def list_orders(
    search: str = Query("", max_length=200),
    status: str = Query("", max_length=30),
    db: Session = Depends(get_db),
) -> list[dict]:
    statement = select(Order).order_by(desc(Order.created_at))
    if search:
        statement = statement.where(or_(Order.link.ilike(f"%{search}%"), Order.service_name.ilike(f"%{search}%")))
    if status:
        statement = statement.where(Order.status == status)
    return [serialize_order(order) for order in db.scalars(statement).all()]


@app.get("/api/dashboard/kpis")
def dashboard_kpis(db: Session = Depends(get_db)) -> dict:
    revenue = db.scalar(select(func.coalesce(func.sum(Order.customer_price), 0)).where(Order.status.in_(["paid", "processing", "completed"]))) or 0
    cost = db.scalar(select(func.coalesce(func.sum(Order.provider_cost), 0)).where(Order.status.in_(["paid", "processing", "completed"]))) or 0
    total = db.scalar(select(func.count(Order.id))) or 0
    completed = db.scalar(select(func.count(Order.id)).where(Order.status == "completed")) or 0
    return {"revenue": round(revenue, 2), "provider_cost": round(cost, 2), "profit": round(revenue - cost, 2), "sales": total, "completed": completed}


def _process_payment(payment_id: str, db: Session) -> None:
    payment = verificar_pagamento(payment_id)
    if payment.get("status") != "approved":
        return
    order = db.scalar(select(Order).where(Order.external_payment_id == str(payment_id)))
    if not order or order.status != "pending":
        return
    order.status = "paid"
    order.paid_at = datetime.utcnow()
    try:
        provider_result = enviar_pedido_smm(order.link, order.quantity, order.service_id, order.comentarios)
        order.provider_order_id = str(provider_result["order"])
        order.status = "processing"
    except Exception:
        order.status = "paid"
        db.commit()
        raise
    db.commit()


@app.post("/webhook/mercadopago")
async def mercadopago_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    body = await request.json()
    payment_id = body.get("data", {}).get("id") or body.get("id")
    if payment_id:
        try:
            _process_payment(str(payment_id), db)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Falha ao processar pagamento {payment_id}: {exc}") from exc
    return {"received": True, "processed": bool(payment_id)}


@app.get("/api/pedidos/exportar")
def export_orders(db: Session = Depends(get_db)) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Plataforma", "Tipo", "Link", "Serviço", "Quantidade", "Custo fornecedor", "Valor cliente", "Lucro", "Status", "Criado em"])
    for order in db.scalars(select(Order).order_by(desc(Order.created_at))).all():
        writer.writerow([order.id, order.plataforma, order.tipo_servico, order.link, order.service_name, order.quantity, order.provider_cost, order.customer_price, order.customer_price - order.provider_cost, order.status, order.created_at.isoformat()])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=relatorio-pedidos.csv"})
