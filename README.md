# Noticias de ATEEZ en Telegram

Revisa varias fuentes cada 15 minutos y te manda por Telegram cada noticia nueva, con el titular traducido al español.
Lo que huele a concierto o entradas llega marcado con 🎫 y `#concierto_entradas` (búscalo en el chat para ver solo eso).

## Fuentes

| Fuente | Qué trae |
|---|---|
| Web oficial `ateez.kqent.com` | Avisos oficiales (membresía ATINY, eventos) |
| YouTube oficial | Cada vídeo nuevo |
| Google News en español, inglés y coreano | Prensa, incluida la coreana |
| Soompi, Koreaboo | Solo los artículos que mencionan a ATEEZ |
| Reddit r/ATEEZ | Comunidad de fans: recopila lo que publican en X, Instagram, etc. |

No cubre directamente X/Twitter, Instagram, Weverse ni el fancafe de Daum: no tienen acceso público gratuito. Lo que salga allí llega cuando lo recoge Reddit o la prensa.

## Puesta en marcha

### 1. Crear el bot

1. En Telegram, abre un chat con **@BotFather** y envía `/newbot`. Ponle nombre.
2. Copia el token que te da (`123456:ABC...`). No lo compartas ni lo subas al repositorio.
3. Abre el chat de tu bot nuevo y envíale `/start`.

### 2. Obtener tu chat id

En PowerShell, dentro de esta carpeta:

```powershell
pip install -r requirements.txt
$env:TELEGRAM_BOT_TOKEN = "TU_TOKEN"
python bot.py --chat-id
```

### 3. Probar en tu PC

```powershell
$env:TELEGRAM_CHAT_ID = "TU_CHAT_ID"
python bot.py
```

La primera ejecución manda solo las 5 noticias más recientes y anota el resto como ya vistas. Desde ahí, solo lo nuevo.
`python bot.py --dry-run` muestra lo que enviaría sin enviar nada.

### 4. Dejarlo funcionando solo (GitHub Actions)

1. Crea un repositorio en GitHub y sube esta carpeta, incluido `seen.json` si ya existe.
2. En el repositorio: **Settings → Secrets and variables → Actions → New repository secret**. Crea `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.
3. En la pestaña **Actions**, abre "Noticias ATEEZ" y pulsa **Run workflow** para la primera ejecución.

Repositorio **público**: gratis sin límite. Repositorio **privado**: el plan gratuito da 2000 minutos al mes y cada 15 minutos gasta unos 2900; cambia el cron de `.github/workflows/noticias.yml` a `*/30 * * * *`.

## Ajustes

Todo está al principio de `bot.py`:

- `SOURCES`: quita o añade fuentes. Si llegan demasiados mensajes, la que más ruido mete es "Google News Corea".
- `TICKET_RE`: palabras que marcan una noticia como concierto/entradas.
- `MAX_PER_RUN`: máximo de mensajes por ejecución; lo que sobra sale en la siguiente.
