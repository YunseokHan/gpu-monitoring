# Embedding the dashboard in Notion

## 1. Get an HTTPS URL

Notion pages are served over HTTPS, so an `http://` iframe is blocked as mixed content —
the dashboard needs a real HTTPS address. The iframe is loaded by *the reader's browser*,
not by Notion's servers, so the address has to be reachable from wherever people read the
page.

```bash
bash deploy/tunnel.sh start
```

This downloads `cloudflared` if needed and opens a quick tunnel, printing something like
`https://calm-river-1234.trycloudflare.com`. Only outbound connections are made: no port
is opened and no inbound firewall rule is required.

**Quick tunnels get a new random hostname every restart.** That is fine for trying things
out, but it means re-pasting the URL into Notion each time. For something permanent, use a
named tunnel with a domain you control:

```bash
cloudflared tunnel login
cloudflared tunnel create gpu-monitoring
cloudflared tunnel route dns gpu-monitoring gpu.example.com
cloudflared tunnel run --url http://127.0.0.1:8000 gpu-monitoring
```

## 2. Pick the right URL

```bash
bash deploy/hubctl.sh tokens
```

| URL | Effect |
|---|---|
| `https://…/` | read-only; the dashboard shows a `READ-ONLY` badge and the dummy switches are disabled |
| `https://…/?k=<control token>` | full control of the dummy switches |

Anyone who can open the page can *see* the cluster, so treat the bare URL as the shareable
one and the `?k=` variant as the operator link. If the page must not be publicly readable
at all, put Cloudflare Access in front of the tunnel — but note that an Access login
prompt cannot be completed inside a Notion iframe, so viewers would have to open it in a
tab.

Optional query parameters:

| Parameter | |
|---|---|
| `?theme=dark` / `?theme=light` | pin the theme. An iframe cannot detect the surrounding Notion page's theme, so without this it follows the viewer's OS setting. |

## 3. Insert the embed block

1. In the Notion page, type `/embed` and pick **Embed**.
2. Paste the URL and click **Embed link**.
3. Drag the bottom edge of the block to size it — one node with 8 GPUs needs roughly
   900 px of height at Notion's default page width.

If you paste the URL directly into the page instead, Notion may offer to create a
**bookmark**; that renders a static preview card, not the live dashboard. Choose
**Create embed**.

The hub sends `Content-Security-Policy: frame-ancestors … notion.so notion.site` and never
sends `X-Frame-Options`, which is what allows the embed. To embed it somewhere else too,
extend `GPU_HUB_FRAME_ANCESTORS` in `deploy/hub.env`.

## 4. Check it

The header shows a green dot and `live · now` when frames are arriving. If it says
`reconnecting`, the tunnel or the hub is down:

```bash
bash deploy/hubctl.sh status
bash deploy/tunnel.sh status
```

## Notes on layout

The dashboard is built for a narrow iframe: GPU cards collapse to one column below
~640 px, two up to ~1280 px, and the page itself never scrolls sideways. Notion's embed
block is fixed-height with its own scrollbar, so making the block taller shows more GPUs
rather than shrinking them.
