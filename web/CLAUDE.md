# Sitio web de ln2oc (`web/`)

Sitio estático React 18 + Vite 5 + TypeScript, **multi-página** (no SPA): `/`, `/usuario/`, `/flujo/`, `/operadores/`, `/arquitectura/`. Lo sirve su propio nginx (`Dockerfile`, `nginx.conf`, puerto 8080, `try_files ... =404`). FastAPI no sirve nada del front: solo redirige `GET /` a `FRONTEND_URL`.

```bash
npm ci
npm test                                            # vitest: lib/address y lib/fees
VITE_API_URL=http://127.0.0.1:8000 npm run dev      # dev server (5173)
npm run build                                       # tsc --noEmit && vite build → dist/
docker compose up -d --build web                    # PUBLIC_API_URL fija la URL de la API al construir
```

## Estructura

| Ruta | Rol |
|---|---|
| `index.html`, `<página>/index.html` | Entradas HTML; cada una carga `src/entries/<página>.tsx`. Se registran en `vite.config.ts` |
| `src/pages/` | Contenido de cada página, portado del artifact maestro (ver `CLAUDE.md` raíz). Si cambia el flujo del swap, actualizar páginas y artifact |
| `src/flujo/animation.js` | Script canvas del artifact envuelto como `mountFlow(root)`, que devuelve un cleanup. JS plano a propósito |
| `src/lib/info.ts` | `useInstanceInfo()`: lee `GET /api/info` (una vez, memoizado). Si falla, usa `DEFAULT_INFO` y el footer dice "sin conexión" |
| `src/lib/address.ts` | Validador de direcciones según la red (espejo liviano de `app/validator.py`; el backend vuelve a validar) |
| `src/lib/fees.ts` | Mismo cálculo de payout que `app/fees.py` (enteros, basis points). Mantenerlos iguales |
| `src/components/` | `Layout` (nav, footer con versión/commit, banner de halt), `AddressMaker`, `SwapLedger` |

## Reglas

- Los valores de la instancia (red, dominio, comisión, mínimos, minería, intervalo de polling) salen de `/api/info`, no hardcodeados. Si se agrega un parámetro, agregarlo en `app/info.py`, `InstanceInfo` y `DEFAULT_INFO`.
- `VITE_API_URL` queda fija en el build; en producción hay que pasarla (p. ej. `https://ln2oc.com`).
- El nav tiene links a GitHub y al Telegram de contacto (`VITE_CONTACT_TELEGRAM`, compose `CONTACT_TELEGRAM`; por defecto `LucasJeffreyP2P`, el del usuario). Cada operador pone el suyo.
- Versiones de dependencias fijadas exactas en `package.json`.
