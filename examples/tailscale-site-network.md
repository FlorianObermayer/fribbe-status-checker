# Tailscale site network setup

How to run the app on a host that is **not** in the router's LAN, while the router itself stays
behind carrier-grade NAT (CGNAT) and accepts no inbound connections.

The app keeps polling the router's Huawei HiLink API over Tailscale; the reverse direction (users
reaching the web UI) is unaffected and stays public HTTPS.

## Topology

```mermaid
flowchart LR
  L["Laptop / phone<br/>(tailnet member)"] -. full access to 192.168.8.0/24 .- P
  U["Public users"] -->|"HTTPS 443"| C["Caddy on Docker VM"]
  C -->|"127.0.0.1:8007"| A["App container"]
  A -->|"100.101.185.7:8080"| P["Raspberry Pi (fribbepi)<br/>site anchor, tag:external-client"]
  P -->|"192.168.8.1:80"| R["LTE router<br/>CGNAT, no inbound"]
  A -. "no subnet route installed" .- X(( ))
```

Two independent paths into the site LAN, with very different privilege:

| Path | Node | Mechanism | Blast radius |
| --- | --- | --- | --- |
| Members (you) | any tailnet member | advertises `192.168.8.0/24`, member ACL `dst: *:*` | full site LAN |
| App VM | `tag:app-server` | single TCP forwarder on the Pi, port 8080 | one port, one fixed destination |

The app VM deliberately does **not** accept the subnet route. Because it runs 30+ unrelated
containers, a route to the whole LAN would grant every one of them access to the site network —
Tailscale ACLs cannot distinguish containers, only the host's tailnet identity.

## Prerequisites

- The Pi is already a tailnet node tagged `tag:external-client` with key expiry disabled.
- The Pi advertises `192.168.8.0/24`, approved in the admin console.
- Tailscale on both hosts; version 1.58 or newer for `tailscale set`.
- You know the Pi's tailnet IPv4 (`tailscale ip -4` on the Pi, `100.101.185.7` in the example below)
  and the router's LAN address (`192.168.8.1` in the example below).

## Part 1 — Raspberry Pi (site anchor)

### 1.1 Re-assert the advertised subnet route

Use `tailscale set`, not `tailscale up`: it changes a single preference and leaves tags,
authentication and every other setting untouched.

```sh
sudo tailscale set --advertise-routes=192.168.8.0/24
tailscale status --json | jq -r '.Self.PrimaryRoutes[]?'
```

The last command must print `192.168.8.0/24`. If the admin console shows the route as approved but
this list is empty, the node stopped advertising and members (including your laptop) will silently
lose LAN access.

### 1.2 Enable IP forwarding

Required for the advertised subnet — approved route plus `net.ipv4.ip_forward=0` means packets
arrive at the Pi and are dropped. The forwarder in 1.3 does not need it, but the laptop path does.

```sh
sysctl net.ipv4.ip_forward      # must print 1

printf 'net.ipv4.ip_forward=1\nnet.ipv6.conf.all.forwarding=1\n' | sudo tee /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
```

Leave `--snat-subnet-routes` at its default (`true`). Consumer hardware on the site LAN usually
cannot route replies back to a `100.64.0.0/10` source address, and SNAT to the Pi's LAN IP
(`192.168.8.174`) avoids that. Consequence: the router's admin UI logs the Pi as the client, not
the app VM.

### 1.3 Install the router forwarder

```sh
sudo apt-get update && sudo apt-get install -y socat
sudo install -m 0644 fribbe-router-forwarder.service /etc/systemd/system/fribbe-router-forwarder.service
sudo systemctl daemon-reload
sudo systemctl enable --now fribbe-router-forwarder
systemctl status fribbe-router-forwarder --no-pager
```

The unit ships with three overridable values. Adjust them for your network without editing the file:

```sh
sudo systemctl edit fribbe-router-forwarder     # add [Service] Environment=... lines
```

- `FORWARD_LISTEN_ADDR` — the Pi's Tailscale IPv4 address. Keep it pinned to the tailnet address so
  the forwarder is unusable from the site LAN.
- `FORWARD_LISTEN_PORT` — `8080` by default; any unprivileged port works.
- `ROUTER_ADDR` — the router's web UI as `host:port`.

### 1.4 Verify on the Pi

```sh
ss -lntp | grep 8080                                    # listening on 100.101.185.7:8080
curl -sS -o /dev/null -w '%{http_code}\n' http://192.168.8.1/     # router answers locally
curl -sS -o /dev/null -w '%{http_code}\n' http://100.101.185.7:8080/  # forwarder works
journalctl -u fribbe-router-forwarder -n 20 --no-pager
```

## Part 2 — Docker VM (application host)

### 2.1 Install Tailscale on the VM, not in a container

```sh
curl -fsSL https://tailscale.com/install.sh | sh
```

`tailscaled` belongs on the VM host. A containerized Tailscale would need `network_mode: host`,
`/dev/net/tun` and kernel mode, and would still put the node identity in a different lifecycle than
the VM. On the host, the default Docker bridge SNATs container traffic to the VM's IP, which routes
over `tailscale0` — so the app container reaches the tailnet with no extra configuration.

Do not install it on the Proxmox host: Tailscale node state is tied to the guest, so live migration
keeps working, and the shared hypervisor stays out of the trust path.

### 2.2 Join with a tag and without route acceptance

Add the tag to `tagOwners` first (Part 3), otherwise the join fails with a tag-not-permitted error.

```sh
sudo tailscale up --authkey=tskey-auth-... \
  --advertise-tags=tag:app-server \
  --accept-routes=false \
  --accept-dns=false

# idempotent re-application on an existing node
sudo tailscale set --advertise-tags=tag:app-server --accept-routes=false --accept-dns=false
```

`--accept-routes=false` is the core of the isolation: without it, every container on this VM could
reach the entire site LAN. `--accept-dns=false` leaves `/etc/resolv.conf` alone, which avoids the
classic Docker pitfall where MagicDNS's `100.100.100.100` is copied into container resolver configs
and name resolution breaks whenever `tailscaled` restarts. Address the Pi by IP, never by MagicDNS
name.

Applying a tag to an existing node may trigger a re-authentication; follow the printed URL if so.

### 2.3 Point the app at the forwarder

`ROUTER_IP` may be `host:port`; the code builds `http://{ROUTER_IP}`.

```sh
ROUTER_IP=100.101.185.7:8080
```

`ROUTER_USERNAME` and `ROUTER_PASSWORD` are unchanged — credentials are still the router's own.

### 2.4 Publish the app port to loopback only

Caddy runs on the same VM, so nothing outside the host needs the container port:

```yaml
    ports:
      - 127.0.0.1:8007:80
```

Then block e.g. `8007` at the VM firewall; the only public ingress should be `80` and `443`.

### 2.5 Reverse proxy and forwarded headers

The app has no `ProxyHeadersMiddleware`, and `app/routers/notification_ui.py` generates absolute
redirects via `request.url_for(...)`. Without forwarded-header trust those redirects emit
`http://<container-host>/...` instead of the public HTTPS URL. Uvicorn trusts forwarded headers
only from `FORWARDED_ALLOW_IPS` (default `127.0.0.1`), which the container never sees.

```sh
docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}'   # e.g. 172.17.0.1
```

Add to the service environment:

```yaml
      - FORWARDED_ALLOW_IPS=172.17.0.1
```

`*` also works and is acceptable here because the port is bound to loopback — but the explicit
gateway is tighter and survives a Docker restart with a different address better than a stale guess.

Minimal Caddyfile:

```caddyfile
status.example.org {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8007
}
```

Caddy sets `X-Forwarded-Proto`, `X-Forwarded-For` and `X-Forwarded-Host` automatically and obtains
the certificate via ACME. Set the app environment accordingly:

```sh
APP_URL=https://status.example.org
HTTPS_ONLY=true
CSP_DOMAIN=status.example.org
```

`HTTPS_ONLY` marks the session and CSRF cookies `Secure`/`https-only`; it does not perform the HTTP →
HTTPS redirect, which Caddy handles.

### 2.6 Verify from the VM and from inside the container

```sh
tailscale status                                            # Pi listed
ip route show table all | grep 192.168.8                    # must be EMPTY
curl -sS -m 5 http://192.168.8.1/ ; echo "exit=$?"          # must FAIL (isolation works)
curl -sS -m 10 -o /dev/null -w '%{http_code}\n' http://100.101.185.7:8080/

docker compose up -d
docker compose exec server python -c \
  "import urllib.request; print(urllib.request.urlopen('http://100.101.185.7:8080/', timeout=10).status)"
docker compose logs --tail 50 server | grep -i presence
curl -sSI https://status.example.org/ | head -n 5
```

An empty `ip route` result and a failing direct `192.168.8.1` request are the proof that the VM
cannot reach the site LAN beyond the forwarder.

## Part 3 — ACL policy

```jsonc
{
  "acls": [
    // You (tailnet member) - full access, including the site LAN via the Pi's subnet route
    { "action": "accept", "src": ["autogroup:member"], "dst": ["*:*"] },

    // fribbepi (external, physical access risk) - only PBS port 8007
    { "action": "accept", "src": ["tag:external-client"], "dst": ["tag:pbs-extern:8007"] },

    // Shared users - only PBS port 8007
    { "action": "accept", "src": ["autogroup:shared"], "dst": ["tag:pbs-extern:8007"] },

    { "action": "accept", "src": ["autogroup:member"], "dst": ["tag:external-client:*"] },

    // NEW: app VM -> the single router forwarder on the Pi, nothing else
    { "action": "accept", "src": ["tag:app-server"], "dst": ["tag:external-client:8080"] },
  ],

  "tagOwners": {
    "tag:pbs-extern":      ["florian.obermayer@gmail.com"],
    "tag:external-client": ["florian.obermayer@gmail.com"],
    "tag:app-server":      ["florian.obermayer@gmail.com"],
  },

  "nodeAttrs": [
    { "target": ["autogroup:member"], "attr": ["funnel"] },
  ],
}
```

Why this shape:

- A **tagged** node is governed only by tag rules, so `tag:app-server` is excluded from the broad
  `autogroup:member` rule. Its only tailnet permission is the forwarder port.
- The destination is the **Pi** (`tag:external-client:8080`), not `192.168.8.1`, because the VM holds
  no subnet route. No route, no subnet-address rules needed.
- Your laptop keeps full LAN access through `autogroup:member → *:*`. Subnet-route destinations are
  matched by that rule, so nothing else has to change for the member path.
- Outbound internet traffic (occupancy scraping, OpenWeatherMap, push delivery) is not subject to
  tailnet ACLs, so tagging the VM does not break the app's other integrations.

## Part 4 — Migration checklist

1. Copy persistent state — the app keeps sessions, `internal/wardens.json`,
   `notifications.json`, `presence_thresholds` and `push_subscriptions.json` in the `app-data`
   volume, plus API keys in `secrets`:

   ```sh
   # on the Pi
   docker volume ls
   docker run --rm -v <project>_app-data:/d -v "$PWD":/out alpine tar czf /out/app-data.tgz -C /d .
   docker run --rm -v <project>_secrets-data:/d -v "$PWD":/out alpine tar czf /out/secrets-data.tgz -C /d .
   ```

   Extract into equivalent volumes on the VM. Losing them drops every push subscription and warden
   mapping.

2. **Stop the old stack on the Pi.** Two instances would poll the same router, both write their own
   copies of the state, and both fire presence pushes to the same subscriptions.

   ```sh
   docker compose down          # keep volumes for rollback
   ```

3. Start the stack on the VM, wait one polling interval (~60 s), then confirm
   `docker compose logs server | grep -i presence` shows a successful refresh and that
   `/api/status` reports a real level rather than `empty`.

4. Keep the Pi's volumes untouched for at least a day as a rollback path.

## Part 5 — Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `tailscale up` fails: tag not permitted | `tag:app-server` missing from `tagOwners` |
| VM cannot reach the Pi's `100.x` address | ACL tag mismatch — tagged nodes need tag rules; untagged nodes match `autogroup:member` |
| `curl http://192.168.8.1` works from the VM | `--accept-routes` still enabled; run `tailscale set --accept-routes=false` |
| Laptop lost LAN access | Pi stopped advertising; re-run `tailscale set --advertise-routes=...` |
| Route approved, members still cannot reach the LAN | `net.ipv4.ip_forward=0` on the Pi |
| Presence polls time out, other traffic fine | Container MTU is 1500 while `tailscale0` is 1280 — set the Docker network MTU to `1280` |
| Container cannot reach the tailnet at all | `ufw` on the VM intercepting `FORWARD`; check the `DOCKER-USER` chain or disable `ufw` on a Docker host |
| Redirects point at `http://` after login | `FORWARDED_ALLOW_IPS` not set to the Docker bridge gateway |
| Custom Docker network in `100.64.0.0/10` | Collides with the Tailscale CGNAT range — renumber the network |

## Part 6 — Known application gaps on a remote link

These are not fixed by the network setup and should be handled separately:

- `InternalService._run_internal_query` calls `huawei_lte_api.Connection` **without** a timeout,
  unlike `PresenceLevelService` (10 s). A stalled relayed connection pins the polling thread
  indefinitely.
- Both pollers set `PresenceLevel.EMPTY` on **any** exception. A tailnet or DERP hiccup therefore
  reports "the beach is empty" to unauthenticated API callers. Transient unreachability should be
  distinguishable from a genuine empty device list.
