from pydantic import BaseModel, Field, field_validator


class ExchangePreset(BaseModel):
    title: str
    exchange_code: str
    default_icon_path: str | None = None
    index: int


class ExchangeCredentialBase(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    exchange_code: str = Field(min_length=1, max_length=64)
    icon_path: str | None = None
    sort_index: int = 0
    is_active: bool = True
    is_futures_enabled: bool = True

    @field_validator("title", "exchange_code")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Field is required")
        return value.strip()


class ExchangeCredentialCreate(ExchangeCredentialBase):
    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)
    password: str | None = None


class ExchangeCredentialUpdate(ExchangeCredentialBase):
    api_key: str | None = None
    api_secret: str | None = None
    password: str | None = None
