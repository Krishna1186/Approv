"""Strict JSON configuration with pinned assets and file-mounted secrets."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from approv.receipts.chain import canonical, canonical_json, key_id_for
from approv.types.core import CategorySchema


class ConfigError(ValueError):
    """Safe to display: never includes configuration values or secret contents."""


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_json(data: str | bytes):
    def invalid(value):
        raise ValueError("non-finite JSON number")
    return json.loads(data, object_pairs_hook=_unique, parse_constant=invalid)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Asset(Strict):
    path: Path
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SecretFile(Strict):
    file: Path

    def read(self, base: Path) -> bytes:
        try:
            path = (base / self.file).resolve()
            # Mounted secrets may be symlinks (e.g. projected volumes); check the target.
            if os.name == "posix" and path.stat().st_mode & 0o077:
                raise ValueError("secret must be accessible only to its service owner")
            data = path.read_bytes()
            # One terminal newline is a file convention, not part of the credential.
            data = data.removesuffix(b"\n").removesuffix(b"\r")
            if not data.strip() or len(data) > 16384 or b"\n" in data or b"\r" in data:
                raise ValueError("invalid secret")
            return data
        except (OSError, ValueError):
            raise ConfigError("required secret unavailable or insecure") from None


class LocalSigning(Strict):
    backend: Literal["encrypted-file"]
    directory: Path
    password: SecretFile
    key_id: str


class KMSSigning(Strict):
    backend: Literal["aws-kms"]
    region: str = Field(min_length=1)
    key_arn: str = Field(pattern=r"^arn:[^:]+:kms:[^:]+:[0-9]{12}:key/[a-zA-Z0-9-]+$")
    key_id: str
    timeout_seconds: float = Field(default=5, gt=0, le=30)


class Prices(Strict):
    # Estimates, explicitly supplied by the operator, never a baked-in provider price.
    input_per_million_usd: float = Field(ge=0, allow_inf_nan=False)
    cached_input_per_million_usd: float = Field(ge=0, allow_inf_nan=False)
    output_per_million_usd: float = Field(ge=0, allow_inf_nan=False)
    as_of: str = Field(min_length=1)


class ExtractorConfig(Strict):
    endpoint: str
    model: str = Field(min_length=1)
    prompt_version: Literal["v6"]
    credential: SecretFile
    prices: Prices

    @field_validator("endpoint")
    @classmethod
    def endpoint_is_safe(cls, value):
        parsed = urlsplit(value)
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query or
                parsed.fragment or (parsed.scheme != "https" and not (
                    parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")))):
            raise ValueError("extractor requires HTTPS or loopback HTTP without embedded credentials")
        return value.rstrip("/")


class FloorPolicy(Strict):
    strict_unread: bool = Field(strict=True)
    # The floor itself lives in each pinned CategorySchema.
    returns: dict[str, Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]] = {}


class Deployment(Strict):
    format: Literal["approv-deployment-v1"]
    deployment_id: str = Field(min_length=1)
    merchant_id: str = Field(min_length=1)
    schemas: tuple[Asset, ...] = Field(min_length=1)
    catalogue_reader: str = Field(pattern=r"^[a-zA-Z_][\w.]*:[a-zA-Z_]\w*$")
    extractor: ExtractorConfig
    signing: Annotated[LocalSigning | KMSSigning, Field(discriminator="backend")]
    public_keys: Asset
    store: Path
    api_token: SecretFile
    floor_policy: FloorPolicy
    readiness_ttl_seconds: float = Field(default=60, ge=5, le=300)
    max_body_bytes: int = Field(default=262144, ge=1024, le=1048576)
    max_inflight: int = Field(default=4, ge=1, le=32)
    metrics_window: int = Field(default=10000, ge=100, le=100000)


@dataclass(frozen=True)
class LoadedDeployment:
    settings: Deployment
    base: Path
    schemas: dict[str, CategorySchema]
    reader: object
    public_keys: dict[str, str]
    manifest: dict

    @property
    def digest(self):
        return sha256(canonical_json(self.manifest).encode()).hexdigest()


def _asset(asset: Asset, base: Path):
    data = (base / asset.path).read_bytes()
    if sha256(data).hexdigest() != asset.sha256:
        raise ConfigError("deployment asset digest mismatch")
    return read_json(data)


def load_deployment(path: str | Path | None = None) -> LoadedDeployment:
    """APPROV_CONFIG names one file; no implicit .env, schema discovery or default keys."""
    try:
        location = path or os.environ.get("APPROV_CONFIG")
        if not location:
            raise ConfigError("APPROV_CONFIG is required")
        location = Path(location).resolve()
        settings = Deployment.model_validate(read_json(location.read_bytes()))
        base = location.parent
        schemas = {}
        for asset in settings.schemas:
            payload = _asset(asset, base)
            if payload.get("status") == "confirmed":
                from approv.schema.models import ConfirmedSchema
                schema = ConfirmedSchema.model_validate(payload).category_schema
            else:
                schema = CategorySchema.model_validate(payload)
            if schema.category_id in schemas or not schema.attributes or not schema.floor:
                raise ConfigError("schemas require unique categories, attributes and an explicit floor")
            if not schema.floor <= {a.name for a in schema.attributes}:
                raise ConfigError("schema floor names an unknown attribute")
            schemas[schema.category_id] = schema
        module, name = settings.catalogue_reader.split(":")
        reader = getattr(importlib.import_module(module), name)
        if not callable(reader):
            raise ConfigError("catalogue reader is not callable")
        if settings.catalogue_reader == "approv.surface.verification:evidence_from_snapshot":
            if any(p.field_name.startswith("/") for s in schemas.values() for p in s.field_profiles):
                raise ConfigError("JSON-pointer catalogue profiles require a compatible configured reader")
        publication = _asset(settings.public_keys, base)
        if publication["format"] != "approv-public-keys-v1" or not publication["keys"]:
            raise ConfigError("invalid public-key publication")
        keys = publication["keys"]
        if any(key_id_for(value) != key for key, value in keys.items()):
            raise ConfigError("public-key fingerprint mismatch")
        if settings.signing.key_id not in keys:
            raise ConfigError("active signing key must already be published")
        # The retained manifest has no credentials, filesystem secret paths or account IDs.
        manifest = {"format": "approv-deployment-manifest-v1",
                    "deployment_id": settings.deployment_id,
                    "merchant_id": settings.merchant_id,
                    "schemas": {k: read_json(canonical(v)) for k, v in schemas.items()},
                    "schema_asset_hashes": sorted(a.sha256 for a in settings.schemas),
                    "catalogue_reader": settings.catalogue_reader,
                    "model": settings.extractor.model,
                    "prompt_version": settings.extractor.prompt_version,
                    "floor_policy": settings.floor_policy.model_dump(mode="json"),
                    "prices": settings.extractor.prices.model_dump(mode="json")}
        return LoadedDeployment(settings, base, schemas, reader, keys, manifest)
    except ConfigError:
        raise
    except Exception:
        raise ConfigError("invalid or unavailable deployment configuration") from None
