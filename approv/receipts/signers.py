"""Load the configured signer; no automatic key generation or backend fallback."""
from __future__ import annotations

import secrets

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from approv.config.settings import ConfigError, KMSSigning
from approv.receipts.chain import key_id_for, public_key_hex
from approv.receipts.keys import KeyStore


class KMSSigner:
    """Ed25519 KMS signatures over exactly the bytes used by the offline verifier.

    Approv signs the ASCII SHA-256 hex string as an Ed25519 message. KMS RAW with
    ED25519_SHA_512 preserves that contract; Ed25519ph / DIGEST does not.
    """
    def __init__(self, client, key_arn: str, expected_public: str):
        self._client, self._arn = client, key_arn
        data = client.get_public_key(KeyId=key_arn)
        key = serialization.load_der_public_key(data["PublicKey"])
        if (data["KeyId"] != key_arn or data["KeyUsage"] != "SIGN_VERIFY" or
                data["KeySpec"] != "ECC_NIST_EDWARDS25519" or
                "ED25519_SHA_512" not in data["SigningAlgorithms"] or
                not isinstance(key, Ed25519PublicKey)):
            raise ValueError("KMS key does not implement the receipt signature version")
        self._public = key
        if public_key_hex(self) != expected_public:
            raise ValueError("KMS key differs from the published key")

    def public_key(self):
        return self._public

    def sign(self, message: bytes) -> bytes:
        response = self._client.sign(KeyId=self._arn, Message=message,
                                     MessageType="RAW", SigningAlgorithm="ED25519_SHA_512")
        if response["KeyId"] != self._arn or response["SigningAlgorithm"] != "ED25519_SHA_512":
            raise ValueError("KMS returned a different key or algorithm")
        signature = response["Signature"]
        self._public.verify(signature, message)
        return signature


class SignerLoader:
    def __init__(self, deployment, *, kms_client=None):
        self.deployment = deployment
        self._kms = None
        settings = deployment.settings.signing
        if isinstance(settings, KMSSigning):
            if kms_client is None:
                import boto3
                from botocore.config import Config
                # Workload identity uses the SDK credential chain. No static AWS keys here.
                kms_client = boto3.client("kms", region_name=settings.region, config=Config(
                    connect_timeout=settings.timeout_seconds, read_timeout=settings.timeout_seconds,
                    retries={"total_max_attempts": 1}))
            self._kms = KMSSigner(kms_client, settings.key_arn,
                                  deployment.public_keys[settings.key_id])

    def load(self):
        settings = self.deployment.settings.signing
        if self._kms is not None:
            return self._kms
        directory = self.deployment.base / settings.directory
        if not (directory / "private").is_dir() or not (directory / "public").is_dir():
            raise ConfigError("signing key directory is missing")
        password = settings.password.read(self.deployment.base)
        key = KeyStore(directory, password=password).load_private(settings.key_id)
        if key_id_for(public_key_hex(key)) != settings.key_id:
            raise ConfigError("loaded key does not match deployment")
        return key

    def probe(self):
        key = self.load()
        message = b"approv-readiness-not-a-receipt:" + secrets.token_bytes(32)
        key.public_key().verify(key.sign(message), message)
