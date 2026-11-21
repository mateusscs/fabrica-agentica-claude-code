"""Instala a Fábrica de Software Agêntica (Claude Code) em um projeto.

Copia agentes, hooks e política para <projeto>/.claude e mescla .claude/settings.json sem apagar o que já existe
(ex.: configurações criadas pelo `specify init`). Também acrescenta ao .gitignore os arquivos locais da fábrica.

Uso: python scripts/instalar.py <caminho do projeto>
"""
import json
import shutil
import sys
from pathlib import Path

ORIGEM = Path(__file__).resolve().parent.parent / ".claude"
IGNORAR = [".claude/settings.local.json", ".claude/fabrica/slack-log.jsonl", ".claude/fabrica/hook-debug.jsonl"]


def mesclar(base: dict, novo: dict) -> dict:
    for chave, valor in novo.items():
        if isinstance(valor, dict) and isinstance(base.get(chave), dict):
            mesclar(base[chave], valor)
        elif isinstance(valor, list) and isinstance(base.get(chave), list):
            for item in valor:
                if item not in base[chave]:
                    base[chave].append(item)
        else:
            base[chave] = valor
    return base


def main():
    projeto = Path(sys.argv[1]).resolve()
    destino = projeto / ".claude"
    for pasta in ("agents", "hooks", "fabrica"):
        shutil.copytree(ORIGEM / pasta, destino / pasta, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*.jsonl", "__pycache__"))
        print(f"copiado: .claude/{pasta}/")

    arq = destino / "settings.json"
    atual = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    novo = json.loads((ORIGEM / "settings.json").read_text(encoding="utf-8"))
    arq.write_text(json.dumps(mesclar(atual, novo), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("mesclado: .claude/settings.json")

    gitignore = projeto / ".gitignore"
    linhas = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    faltando = [l for l in IGNORAR if l not in linhas]
    if faltando:
        gitignore.write_text("\n".join(linhas + faltando) + "\n", encoding="utf-8")
        print("atualizado: .gitignore")

    local = destino / "settings.local.json"
    if not local.exists():
        local.write_text(json.dumps({"env": {"SLACK_WEBHOOK_URL": ""}}, indent=2) + "\n", encoding="utf-8")
        print("criado: .claude/settings.local.json (cole a URL do webhook do Slack em SLACK_WEBHOOK_URL)")

    print("\nFábrica instalada. Abra o Claude Code na pasta do projeto: o agente principal já será o orquestrador.")


if __name__ == "__main__":
    main()
