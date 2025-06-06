#!/usr/bin/env python3
import os
from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from pathlib import Path
import time

templates = {
    "green": """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="background-color:lightgreen;">
<h1>Es scheint was los zu sein!</h1>
</body>
</html>""",
    "yellow": """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="background-color:lightyellow;">
<h1>Möglicherweise ist keiner da. Schau doch vorbei und änder das!</h1>
</body>
</html>"""
}

def update_html():
    # 1. Login
    username = os.environ["ROUTER_USERNAME"]
    password = os.environ["ROUTER_PASSWORD"]
    router_ip = os.environ["ROUTER_IP"]
    html_root_path = os.environ["HTML_ROOT_PATH"]

    with Connection('http://'+ username + ':' + password +  '@' + router_ip) as connection:
        client = Client(connection)

        active_devices_ct = len(client.wlan.host_list())
        # 3. HTML aktualisieren
        status = "green" if active_devices_ct > 1 else "yellow"
        output_path = Path(f"{html_root_path}/index.html")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
                f.write(templates[status])

        print(f"Status updated: {status} (# devices: {active_devices_ct})")
        time.sleep(120)

if __name__ == "__main__":
    while True:
        try:
            update_html()
        except Exception as e:
            print(f"Error: {str(e)}")
            time.sleep(30)