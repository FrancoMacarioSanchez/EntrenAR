"""JWT atado al gimnasio: un token emitido en un schema no sirve en otro."""
from django.db import connection
from rest_framework import exceptions, serializers
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken


class TenantJWTAuthentication(JWTAuthentication):
    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        if token.get("schema") != connection.schema_name:
            raise exceptions.AuthenticationFailed("Token de otro gimnasio.", code="wrong_tenant")
        return token


class TenantTokenSerializer(TokenObtainPairSerializer):
    username_field = "username"

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["schema"] = connection.schema_name
        token["role"] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        if self.user.role not in ("student", "trainer", "owner", "admin", "reception"):
            raise serializers.ValidationError("Usuario sin acceso a la app.")
        return data


class TenantRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = RefreshToken(attrs["refresh"])
        if refresh.get("schema") != connection.schema_name:
            raise serializers.ValidationError("Token de otro gimnasio.")
        return super().validate(attrs)
