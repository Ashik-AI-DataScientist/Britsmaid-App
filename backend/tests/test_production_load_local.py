"""Concurrent role-isolation smoke check, not a Render hardware benchmark."""
import asyncio
import pytest
from bson import ObjectId
from test_role_security_local import ctx, server


@pytest.mark.asyncio
async def test_forty_accounts_keep_property_scope_under_concurrent_reads(ctx):
    users = []
    for i in range(40):
        user = {"_id": ObjectId(), "name": f"Synthetic {i}", "email": f"synthetic-{i}@example.com",
            "active": True, "role": ["owner", "cleaner", "supervisor"][i % 3],
            "property_ids": [ctx["p1"] if i % 2 else ctx["p2"]]}
        await ctx["db"].users.insert_one(user)
        users.append(user)
    async def read(user):
        headers = {"Authorization": "Bearer " + server.issue_token(user)}
        response = await ctx["client"].get("/api/properties", headers=headers)
        assert response.status_code == 200
        assert [row["id"] for row in response.json()] == user["property_ids"]
        if user["role"] != "owner":
            assert "owner_phone" not in response.text
        assert (await ctx["client"].get("/api/users", headers=headers)).status_code == 403
    await asyncio.gather(*(read(user) for user in users))
