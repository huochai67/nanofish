# nanofish frontend previews

Screenshot-oriented Next.js views for chat messages, EH search, reverse image search, and parsed social-media links.

## Run

```bash
npm run dev
npm run build
npm run start
```

`dev` and `build` refresh the EH tag dictionary before starting Next.js.

## Data injection

Each page uses its built-in Mock data when no payload is supplied. For screenshot automation, inject data before navigation:

```ts
await page.addInitScript((data) => {
  window.__CHAT_DATA__ = data;
}, chatData);
await page.goto("http://localhost:3000/chat");
await page.locator('[data-ready="ready"]').waitFor();
```

Available globals:

- `/chat`: `window.__CHAT_DATA__`
- `/eh`: `window.__EH_DATA__`
- `/imgsearch`: `window.__IMGSEARCH_DATA__`
- `/parser`: `window.__PARSER_DATA__`

All pages also accept `?data=<utf8-base64-json>` for short, local preview payloads. The home page generates this URL format. Do not use it for large messages, base64 media, or production sharing: browser and proxy URL limits make injected data the reliable option.

## Screenshot readiness

Pages expose `data-ready="pending"` until visible remote media and fonts load. Screenshot automation should wait for `data-ready="ready"` rather than a fixed delay. `data-ready="timeout"` means a remote asset exceeded 10 seconds and the screenshot should be retried or failed rather than captured with unstable pixels.

Payloads from either source are validated at the page boundary. Invalid payloads fall back to the page Mock data and display an error notice.
