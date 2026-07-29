# Publicar R-Bot Industrial en GitHub

Perfil: https://github.com/Rony-Luis-Theodore

## Cursor ↔ GitHub

1. **Cursor → Settings → Account** (o *Integrations*): inicia sesión con GitHub.
   Sirve para PRs, Issues y funciones del editor.
2. **Terminal (push/clone):** autenticación aparte:
   - `gh auth login` (recomendado), o
   - SSH key en https://github.com/settings/keys

Ambas pueden usar la misma cuenta [Rony-Luis-Theodore](https://github.com/Rony-Luis-Theodore).

## Primer push (desde esta máquina)

```bash
cd ~/Documents/Proyectos/rbot-industrial

# Instalar GitHub CLI si falta
# sudo apt install gh   # o: https://cli.github.com/

gh auth login
# GitHub.com → HTTPS → login navegador

# Si aún no hay commit:
# git add -A && git status   # revisar que NO esté .env ni *.gguf
# git commit -m "…"

gh repo create rbot-industrial --public --source=. --remote=origin --push
```

Repo esperado: `https://github.com/Rony-Luis-Theodore/rbot-industrial`

## No subir

- `apps/api/.env` (secretos / lab)
- `ml/export/*.gguf` (~1.8 GB)
- `packages/ros_ws/` (symlink local)
- `_local/` fuera del monorepo
