# Sitio web de ln2oc (`web/`)

Sitio estático React 18 + Vite 5 + TypeScript, **multi-página** (no SPA), separado en dos lugares que se tienen que ver distintos:

- **El sitio** (`/`, `SiteLayout`): usuarios arriba (armar la Lightning Address, animación `user`, costos, FAQ) y community leaders abajo (`/#comunidades`, animación `community`). Opcional y secundario: pedir la invoice desde la web (`LnurlPay`). No está pensado para usarse desde la web: lo normal es la wallet del usuario.
- **Las docs** (`/docs/`, `DocsLayout` con sidebar e insignia "Docs"): `/docs/` (cómo funciona: diagramas de secuencia exitoso/fallido, públicos, supuestos), `/docs/usuarios/`, `/docs/comunidades/`, `/docs/operadores/` (con la animación por dentro `ok`/`fail`), `/docs/desarrolladores/`, `/docs/flujo/`, `/docs/arquitectura/`.

El header pregunta "¿Quién sos?": Usuario → `/`, Community leader → `/#comunidades`, Operador y Desarrollador → sus docs. Las rutas viejas (`/usuario/`, `/operadores/`, …) redirigen con 301 en `nginx.conf`. Lo sirve su propio nginx (`Dockerfile`, puerto 8080, `try_files ... =404`). FastAPI no sirve nada del front: solo redirige `GET /` a `FRONTEND_URL`.

```bash
npm ci
npm test                                            # vitest: lib/address, lib/fees, lib/bolt11
VITE_API_URL=http://127.0.0.1:8000 npm run dev      # dev server (5173)
npm run build                                       # tsc --noEmit && vite build → dist/
docker compose up -d --build web                    # PUBLIC_API_URL fija la URL de la API al construir
```

## Estructura

| Ruta | Rol |
|---|---|
| `index.html`, `docs/**/index.html` | Entradas HTML; cada una carga `src/entries/<página>.tsx`. Se registran en `vite.config.ts`, que además mete una CSP estricta en el build |
| `src/pages/` | Contenido de cada página, portado del artifact maestro (ver `CLAUDE.md` raíz). Si cambia el flujo del swap, actualizar páginas y artifact |
| `src/flujo/animation.js` | Animación canvas, `mountFlow(root, escenario)` (devuelve un cleanup). Escenarios `user`, `community`, `ok`, `fail`. Todo con `data-flow`/`data-scen` dentro de `root` (sin ids): puede haber varias por página; se pausa fuera de pantalla. JS plano a propósito |
| `src/lib/diagrams.ts`, `components/Sequence.tsx` | Diagramas de secuencia en SVG propio (estilo mermaid, sin cargar mermaid). Los mismos están en mermaid en el README: mantenerlos iguales |
| `src/lib/bolt11.ts` | Lee red y monto de una invoice: `LnurlPay` no muestra una invoice que no coincida con lo pedido |
| `src/lib/info.ts` | `useInstanceInfo()`: lee `GET /api/info` (una vez, memoizado). Si falla, usa `DEFAULT_INFO` y el footer dice "sin conexión" |
| `src/lib/address.ts` | Validador de direcciones según la red (espejo liviano de `app/validator.py`; el backend vuelve a validar) |
| `src/lib/fees.ts` | Mismo cálculo de payout que `app/fees.py` (enteros, basis points). Mantenerlos iguales |
| `src/components/` | `Layout` (`SiteLayout`/`DocsLayout`, header "¿Quién sos?", footer con versión/commit, banners de halt y de red de prueba), `AddressMaker` (con `withPay`), `LnurlPay`, `Qr`, `FlowPlayer`, `Sequence`, `SwapLedger` |

## Reglas

- Los valores de la instancia (red, dominio, comisión, mínimos, minería, intervalo de polling) salen de `/api/info`, no hardcodeados. Si se agrega un parámetro, agregarlo en `app/info.py`, `InstanceInfo` y `DEFAULT_INFO`.
- `VITE_API_URL` queda fija en el build; en producción hay que pasarla (p. ej. `https://ln2oc.com`).
- El nav tiene links a GitHub y al Telegram de contacto (`VITE_CONTACT_TELEGRAM`, compose `CONTACT_TELEGRAM`; por defecto `LucasJeffreyP2P`, el del usuario). Cada operador pone el suyo.
- Versiones de dependencias fijadas exactas en `package.json`. Cada dependencia nueva es superficie de ataque en una página que muestra invoices: la única de runtime además de React es `qrcode-generator`.
- Nada de terceros en runtime: sin Google Fonts ni CDNs (fuentes del sistema). La CSP del build (`vite.config.ts`) solo deja conectar al propio sitio y a `VITE_API_URL`.
- `LnurlPay`: el callback LNURL se usa solo por su ruta (`/lnurlp/cb`) contra `VITE_API_URL`, tiene que ser para la misma dirección, y la invoice tiene que ser de la red de la instancia y por el monto pedido. Si algo no coincide, error y nada en pantalla.
- Tema oscuro único (tokens en `styles/base.css`). Colores con significado: `--ln` Lightning, `--btc` on-chain, `--comm` comunidades.
