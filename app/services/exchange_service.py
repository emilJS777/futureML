import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_value, encrypt_value, mask_secret
from app.models.exchange_credential import ExchangeCredential
from app.schemas.exchange_credential import ExchangeCredentialCreate, ExchangeCredentialUpdate, ExchangePreset


EXCHANGE_PRESETS: list[ExchangePreset] = [
    ExchangePreset(title="AscendEX", exchange_code="ascendex", default_icon_path="https://static.coinpaprika.com/coin/ascendex-token-logo.png", index=1),
    ExchangePreset(title="Bitfinex", exchange_code="bitfinex", default_icon_path="https://assets.coingecko.com/markets/images/4/small/BItfinex.png", index=2),
    ExchangePreset(title="MEXC", exchange_code="mexc", default_icon_path="https://assets.coingecko.com/markets/images/409/small/WeChat_Image_20210622160936.png", index=3),
    ExchangePreset(title="Binance", exchange_code="binance", default_icon_path="https://assets.coingecko.com/markets/images/52/small/binance.jpg", index=4),
    ExchangePreset(title="Gate.io", exchange_code="gate", default_icon_path="https://assets.coingecko.com/markets/images/60/small/gate_io_logo1.jpg", index=5),
    ExchangePreset(title="Huobi / HTX", exchange_code="htx", default_icon_path="https://assets.coingecko.com/markets/images/25/small/htx.png", index=6),
    ExchangePreset(title="WhiteBIT", exchange_code="whitebit", default_icon_path="https://assets.coingecko.com/markets/images/418/small/wb_3_avatar-02.png", index=7),
    ExchangePreset(title="Bybit", exchange_code="bybit", default_icon_path="https://assets.coingecko.com/markets/images/698/small/bybit_spot.png", index=8),
    ExchangePreset(title="KuCoin Futures", exchange_code="kucoinfutures", default_icon_path="https://assets.coingecko.com/markets/images/61/small/kucoin.png", index=9),
]

PRESET_BY_CODE = {preset.exchange_code: preset for preset in EXCHANGE_PRESETS}


def validate_exchange_code(exchange_code: str) -> None:
    if exchange_code not in PRESET_BY_CODE:
        valid_codes = ", ".join(PRESET_BY_CODE)
        raise ValueError(f"Unsupported exchange_code. Expected one of: {valid_codes}")


def list_credentials(db: Session) -> list[ExchangeCredential]:
    return list(db.scalars(select(ExchangeCredential).order_by(ExchangeCredential.sort_index, ExchangeCredential.title)))


def get_credential(db: Session, public_id: uuid.UUID) -> ExchangeCredential | None:
    return db.scalar(select(ExchangeCredential).where(ExchangeCredential.public_id == public_id))


def create_credential(db: Session, payload: ExchangeCredentialCreate) -> ExchangeCredential:
    validate_exchange_code(payload.exchange_code)
    credential = ExchangeCredential(
        title=payload.title,
        exchange_code=payload.exchange_code,
        icon_path=payload.icon_path,
        sort_index=payload.sort_index,
        api_key_encrypted=encrypt_value(payload.api_key),
        api_secret_encrypted=encrypt_value(payload.api_secret),
        password_encrypted=encrypt_value(payload.password) if payload.password else None,
        is_active=payload.is_active,
        is_futures_enabled=payload.is_futures_enabled,
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)
    return credential


def update_credential(db: Session, credential: ExchangeCredential, payload: ExchangeCredentialUpdate) -> ExchangeCredential:
    validate_exchange_code(payload.exchange_code)
    credential.title = payload.title
    credential.exchange_code = payload.exchange_code
    credential.icon_path = payload.icon_path
    credential.sort_index = payload.sort_index
    credential.is_active = payload.is_active
    credential.is_futures_enabled = payload.is_futures_enabled
    if payload.api_key:
        credential.api_key_encrypted = encrypt_value(payload.api_key)
    if payload.api_secret:
        credential.api_secret_encrypted = encrypt_value(payload.api_secret)
    if payload.password:
        credential.password_encrypted = encrypt_value(payload.password)
    db.commit()
    db.refresh(credential)
    return credential


def delete_credential(db: Session, credential: ExchangeCredential) -> None:
    db.delete(credential)
    db.commit()


def masked_api_key(credential: ExchangeCredential) -> str:
    return mask_secret(decrypt_value(credential.api_key_encrypted))
