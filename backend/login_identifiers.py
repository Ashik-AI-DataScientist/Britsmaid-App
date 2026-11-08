"""Normalised login identifiers; phone numbers are identifiers, not OTP login."""
import re
from fastapi import HTTPException


def phone_key(value):
    value = (value or "").strip()
    if not value:
        return ""
    if not re.fullmatch(r"[+\d\s()-]+", value):
        raise HTTPException(422, "Enter a phone number with country code")
    digits = re.sub(r"\D", "", value)
    if len(digits) == 10 and not value.startswith("+"):
        digits = "91" + digits
    if not 8 <= len(digits) <= 15:
        raise HTTPException(422, "Enter a valid phone number; include country code outside India")
    return "+" + digits


def aliases(user):
    values = []
    if user.get("email"):
        values.append(user["email"].strip().lower())
    if user.get("username"):
        name = user["username"].strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{2,39}", name):
            raise HTTPException(422, "Username must be 3–40 characters, start with a letter, and use letters, numbers, dots, _ or -")
        values.append(name)
    if user.get("phone"):
        values.append(phone_key(user["phone"]))
    if not values:
        raise HTTPException(422, "Provide an email, phone number or username for sign-in")
    return values


def legacy_aliases(user):
    try:
        return aliases(user)
    except HTTPException:
        return [str(user.get(k) or "").strip().lower() for k in ("email", "username") if user.get(k)]


async def matching_users(db, identifier):
    value = identifier.strip().lower()
    if "@" not in value and re.fullmatch(r"[+\d\s()-]+", value):
        try:
            value = phone_key(value)
        except HTTPException:
            return []
    # Legacy accounts may have formatted contact numbers and no alias field.
    # Ambiguous matches deliberately fail; never choose an arbitrary account.
    users = await db.users.find({"$or": [{"login_aliases": value}, {"login_aliases": {"$exists": False}}]}).to_list(None)
    return [u for u in users if value in legacy_aliases(u)]


async def validate_unique(db, proposed, exclude=None):
    wanted = aliases(proposed)
    users = await db.users.find({}).to_list(None)
    for user in users:
        if user.get("_id") != exclude and set(wanted).intersection(legacy_aliases(user)):
            raise HTTPException(409, "Email, phone or username already belongs to another account")
    return wanted
