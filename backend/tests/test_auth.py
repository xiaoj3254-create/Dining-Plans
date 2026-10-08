"""M1 验收：注册/登录/JWT/实名/脱敏"""

from tests.conftest import API, VALID_ID_CARD, register


def test_register_login_me(client):
    data = register(client, "alice", nickname="小红", age=26, gender="female")
    assert data["access_token"]
    assert data["user"]["nickname"] == "小红"

    headers = {"Authorization": f"Bearer {data['access_token']}"}
    r = client.get(f"{API}/auth/me", headers=headers)
    assert r.status_code == 200
    me = r.json()
    assert me["username"] == "alice"
    assert me["real_name_verified"] is False
    assert me["consent_version"] is not None  # 注册即留痕同意版本


def test_register_without_consent_422(client):
    """PIPL：未同意协议不得注册"""
    r = client.post(f"{API}/auth/register", json={
        "username": "noconsent", "password": "pass123456",
        "nickname": "无同意", "age": 25, "gender": "male", "consent": False,
    })
    assert r.status_code == 422
    assert "协议" in r.json()["detail"]


def test_underage_register_rejected(client):
    """18 岁门槛：原实现 gt=0，1 岁即可注册并参与线下拼桌"""
    r = client.post(f"{API}/auth/register", json={
        "username": "kid", "password": "pass123456",
        "nickname": "未成年", "age": 15, "gender": "male", "consent": True,
    })
    assert r.status_code == 422


def test_duplicate_username_409(client):
    register(client, "bob")
    r = client.post(f"{API}/auth/register", json={
        "username": "bob", "password": "pass123456",
        "nickname": "bob2", "age": 30, "gender": "male", "consent": True,
    })
    assert r.status_code == 409


def test_login_wrong_password(client):
    register(client, "carl")
    r = client.post(f"{API}/auth/login", json={"username": "carl", "password": "wrong-pass"})
    assert r.status_code == 401


def test_me_requires_token(client):
    r = client.get(f"{API}/auth/me")
    assert r.status_code == 401


def test_realname_flow(client):
    data = register(client, "dave")
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    r = client.post(f"{API}/users/me/realname",
                    json={"real_name": "李四", "id_card": VALID_ID_CARD, "consent": True},
                    headers=headers)
    assert r.status_code == 200
    assert r.json()["real_name_verified"] is True

    # 未实名拦截：广场访问 403
    r2 = client.get(f"{API}/plaza/teams", headers={"Authorization": f"Bearer {register(client, 'eve')['access_token']}"})
    assert r2.status_code == 403


def test_realname_requires_consent(client):
    """敏感个人信息需单独同意"""
    data = register(client, "dave2")
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    r = client.post(f"{API}/users/me/realname",
                    json={"real_name": "李四", "id_card": VALID_ID_CARD, "consent": False},
                    headers=headers)
    assert r.status_code == 422


def test_realname_rejects_invalid_id_card(client):
    """原实现只校验长度：real_name="ab" + id_card="123456" 即可通过"实名认证"。"""
    data = register(client, "dave3")
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    for payload in (
        {"real_name": "李四", "id_card": "123456789012345678", "consent": True},   # 校验位错
        {"real_name": "ab", "id_card": VALID_ID_CARD, "consent": True},            # 姓名格式错
    ):
        assert client.post(f"{API}/users/me/realname", json=payload, headers=headers).status_code == 422


def test_realname_locks_age(client):
    """实名后年龄以证件为准并被锁定，不能改年龄绕过门槛"""
    data = register(client, "dave4")
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    client.post(f"{API}/users/me/realname",
                json={"real_name": "李四", "id_card": VALID_ID_CARD, "consent": True},
                headers=headers)
    me = client.get(f"{API}/auth/me", headers=headers).json()
    # 证件出生日期 1990-01-01 → 年龄被修正为证件推算值
    assert me["age"] >= 30
    r = client.patch(f"{API}/users/me", json={"age": 20}, headers=headers)
    assert r.status_code == 409


def test_alipay_mock_login(client):
    r = client.post(f"{API}/auth/alipay", json={
        "code": "mock:wx_user_1", "nickname": "微信用户", "age": 28,
        "gender": "female", "consent": True,
    })
    assert r.status_code == 200
    token = r.json()["access_token"]
    # 再次登录同一 mock code → 同一用户
    r2 = client.post(f"{API}/auth/alipay", json={"code": "mock:wx_user_1"})
    assert r2.json()["user"]["id"] == r.json()["user"]["id"]

    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 200


def test_alipay_new_user_requires_consent(client):
    """新用户必须先同意协议，否则静默登录会变成"未经同意处理个人信息"的后门"""
    r = client.post(f"{API}/auth/alipay", json={"code": "mock:brand_new_user"})
    assert r.status_code == 422


def test_account_delete_anonymizes_and_revokes_token(client):
    data = register(client, "delme", nickname="要注销")
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    assert client.delete(f"{API}/users/me", headers=headers).status_code == 200
    # 旧 token 立即失效（token_version 递增）
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 401
    # 同名再登录：密码已清除
    assert client.post(f"{API}/auth/login",
                       json={"username": "delme", "password": "pass123456"}).status_code == 401
