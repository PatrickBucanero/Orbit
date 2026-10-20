from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    external_payment_id: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    link: Mapped[str] = mapped_column(String(500), nullable=False)
    plataforma: Mapped[str] = mapped_column(String(40), nullable=False, default="Instagram")
    tipo_servico: Mapped[str] = mapped_column(String(60), nullable=False, default="seguidores")
    comentarios: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_id: Mapped[str] = mapped_column(String(80), nullable=False)
    service_name: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_cost: Mapped[float] = mapped_column(Float, nullable=False)
    customer_price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    pix_copy_paste: Mapped[str | None] = mapped_column(Text, nullable=True)
    pix_qr_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=func.now(), index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def profit(self) -> Decimal:
        return Decimal(str(self.customer_price)) - Decimal(str(self.provider_cost))


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class Configuracao(Base):
    __tablename__ = "configuracoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    smm_api_url: Mapped[str] = mapped_column(String(500), default="")
    smm_api_key: Mapped[str] = mapped_column(Text, default="")
    mercadopago_access_token: Mapped[str] = mapped_column(Text, default="")
    margem_lucro_padrao_porcentagem: Mapped[float] = mapped_column(Float, default=150.0)


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    value: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
