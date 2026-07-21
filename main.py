import time
import webbrowser
import requests

# Официальный Client ID Minecraft
CLIENT_ID = "00000000402b5328"


def get_ms_access_token_device_code():
    """Авторизация через Device Code Flow для MSA (login.live.com)."""
    
    # 1. Запрос кода устройства через эндпоинт Live Connect
    connect_url = "https://login.live.com/oauth20_connect.srf"
    data = {
        "client_id": CLIENT_ID,
        "scope": "XboxLive.signin offline_access",
        "response_type": "device_code"
    }

    res = requests.post(connect_url, data=data)
    res.raise_for_status()
    device_data = res.json()

    user_code = device_data["user_code"]
    verification_uri = device_data.get("verification_uri", "https://microsoft.com/link")
    device_code = device_data["device_code"]
    interval = device_data.get("interval", 5)

    print("\n" + "=" * 50)
    print(f" ВАШ КОД ВХОДА:  {user_code}")
    print(f" Страница входа: {verification_uri}")
    print("=" * 50)
    print("Открытие браузера...")

    # Автоматически открываем страницу ввода кода
    webbrowser.open(verification_uri)

    # 2. Опрос сервера Microsoft (login.live.com) в ожидании ввода кода
    token_url = "https://login.live.com/oauth20_token.srf"
    token_data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": CLIENT_ID,
        "device_code": device_code
    }

    print("\nОжидание подтверждения в браузере...")
    while True:
        time.sleep(interval)
        token_res = requests.post(token_url, data=token_data)
        res_json = token_res.json()

        if "access_token" in res_json:
            print(" Авторизация прошла успешно!")
            return res_json["access_token"]

        error = res_json.get("error")
        if error == "authorization_pending":
            continue
        elif error == "slow_down":
            interval += 5
        elif error == "expired_token":
            raise Exception("Время действия кода истекло. Запустите скрипт снова.")
        else:
            raise Exception(f"Ошибка авторизации: {res_json.get('error_description', error)}")


def get_minecraft_profile(ms_access_token: str):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Minecraft/1.0"
    }

    # 1. Xbox Live
    print("[1/4] Авторизация в Xbox Live...")
    xbl_payload = {
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": f"d={ms_access_token}"
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT"
    }
    xbl_res = requests.post("https://user.auth.xboxlive.com/user/authenticate", json=xbl_payload, headers=headers)
    xbl_res.raise_for_status()
    xbl_data = xbl_res.json()

    xbl_token = xbl_data["Token"]
    user_hash = xbl_data["DisplayClaims"]["xui"][0]["uhs"]

    # 2. XSTS Token
    print("[2/4] Получение XSTS токена...")
    xsts_payload = {
        "Properties": {
            "SandboxId": "RETAIL",
            "UserTokens": [xbl_token]
        },
        "RelyingParty": "rp://api.minecraftservices.com/",
        "TokenType": "JWT"
    }
    xsts_res = requests.post("https://xsts.auth.xboxlive.com/xsts/authorize", json=xsts_payload, headers=headers)
    
    if xsts_res.status_code == 401:
        data = xsts_res.json()
        error_code = data.get("XErr")
        if error_code == 2148916238:
            raise Exception("Учетная запись принадлежит ребенку. Добавьте её в семейную группу Xbox.")
        elif error_code == 2148916233:
            raise Exception("У аккаунта нет профиля Xbox. Создайте его на xbox.com.")
        else:
            raise Exception(f"Ошибка XSTS (Код: {error_code})")

    xsts_res.raise_for_status()
    xsts_data = xsts_res.json()
    xsts_token = xsts_data["Token"]

    # 3. Minecraft Access Token
    print("[3/4] Авторизация в Minecraft Services...")
    mc_payload = {
        "identityToken": f"XBL3.0 x={user_hash};{xsts_token}"
    }
    mc_res = requests.post("https://api.minecraftservices.com/authentication/login_with_xbox", json=mc_payload, headers=headers)
    
    if mc_res.status_code != 200:
        raise Exception(f"Ошибка Minecraft Auth ({mc_res.status_code}): {mc_res.text}")
        
    mc_access_token = mc_res.json()["access_token"]

    # 4. Профиль игрока
    print("[4/4] Запрос профиля Minecraft...")
    auth_headers = {
        "Authorization": f"Bearer {mc_access_token}",
        "User-Agent": headers["User-Agent"]
    }
    profile_res = requests.get("https://api.minecraftservices.com/minecraft/profile", headers=auth_headers)

    if profile_res.status_code == 404:
        raise Exception("На этом аккаунте Microsoft не куплена лицензия Minecraft!")

    profile_res.raise_for_status()
    profile_data = profile_res.json()

    return {
        "mc_access_token": mc_access_token,
        "uuid": profile_data["id"],
        "username": profile_data["name"]
    }


def main():
    try:
        ms_token = get_ms_access_token_device_code()
        mc_info = get_minecraft_profile(ms_token)

        print("\n" + "=" * 50)
        print(" УСПЕШНАЯ АВТОРИЗАЦИЯ MINECRAFT")
        print("=" * 50)
        print(f"Никнейм:          {mc_info['username']}")
        print(f"UUID:             {mc_info['uuid']}")
        print(f"MC Access Token:  {mc_info['mc_access_token']}")
        print("=" * 50)
        print("\nАргументы для передачи клиенту игры:")
        print(f"--username {mc_info['username']} --uuid {mc_info['uuid']} --accessToken {mc_info['mc_access_token']} --userType msa")

    except Exception as e:
        print(f"\nОшибка: {e}")


if __name__ == "__main__":
    main()
