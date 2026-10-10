from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .models import Address, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone_number",
            "is_email_verified",
            "newsletter_opt_in",
            "date_joined",
        ]
        read_only_fields = ["id", "email", "is_email_verified", "date_joined"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)
    first_name = serializers.CharField(max_length=150)

    class Meta:
        model = User
        fields = ["email", "password", "first_name", "last_name", "phone_number", "newsletter_opt_in"]
        # Uniqueness is handled in validate_email so an abandoned, never-verified
        # sign-up can be completed again instead of locking the address out.
        extra_kwargs = {"email": {"validators": []}}

    def validate_email(self, value):
        value = value.lower().strip()
        existing = User.objects.filter(email__iexact=value).first()
        if existing and existing.is_email_verified:
            raise serializers.ValidationError("An account with this email already exists.")
        self._pending_user = existing
        return value

    def validate_first_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Enter your first name.")
        return value

    def validate(self, attrs):
        # Validate against the user's own details so "Jessy2024!" style passwords are caught.
        candidate = User(email=attrs["email"], first_name=attrs.get("first_name", ""), last_name=attrs.get("last_name", ""))
        try:
            password_validation.validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = getattr(self, "_pending_user", None) or User(username=validated_data["email"])
        for field, value in validated_data.items():
            setattr(user, field, value)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(max_length=128, trim_whitespace=False)

    def validate_email(self, value):
        return value.lower().strip()


class VerifyCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.RegexField(r"^\s*\d{6}\s*$", error_messages={"invalid": "Enter the 6-digit code."})

    def validate_email(self, value):
        return value.lower().strip()


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower().strip()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, max_length=128, trim_whitespace=False)

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            raise serializers.ValidationError("Invalid password reset link.")

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError("This password reset link is invalid or has expired.")

        password_validation.validate_password(attrs["new_password"], user)
        attrs["user"] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    # The current password is checked in the view, where wrong guesses count toward the lockout.
    old_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(min_length=8, max_length=128, trim_whitespace=False)

    def validate_new_password(self, value):
        password_validation.validate_password(value, self.context["request"].user)
        return value

    def validate(self, attrs):
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": "Choose a password different from your current one."})
        return attrs


class StartEmailChangeSerializer(serializers.Serializer):
    new_email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)

    def validate_new_email(self, value):
        value = value.lower().strip()
        user = self.context["request"].user
        if value == user.email.lower():
            raise serializers.ValidationError("That's already your email address.")
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("That email address is already in use.")
        return value


class ConfirmEmailChangeSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^\s*\d{6}\s*$", error_messages={"invalid": "Enter the 6-digit code."})


class RevertEmailChangeSerializer(serializers.Serializer):
    token = serializers.CharField()


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id",
            "label",
            "full_name",
            "phone_number",
            "address_line1",
            "address_line2",
            "city",
            "county_or_state",
            "postal_code",
            "country",
            "landmark",
            "latitude",
            "longitude",
            "is_default",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
