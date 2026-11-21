"""Converte os agentes da Fábrica de Software (formato opencode) para subagentes do Claude Code.

Reaproveita o corpo (prompt de sistema) de cada agente original sem reescrevê-lo:
- troca o cabeçalho YAML do opencode pelo cabeçalho do Claude Code (name, description, tools, model);
- move as regras de `permission` para .claude/fabrica/policy.json (aplicadas pelo hook fabrica_guard.py);
- ajusta os identificadores `fabrica-software/subagent-*` para os nomes do Claude Code;
- acrescenta uma nota curta de adaptação ao harness, sem apagar nenhuma regra original.

Uso: python scripts/converter.py <pasta src do repositório original> <pasta .claude de destino>
"""
import json
import re
import sys
from pathlib import Path

# Papel -> configuração no Claude Code. Modelos diferentes nos pares produtor/verificador
# (README original, seção "Um modelo diferente para cada papel").
AGENTES = {
    "orquestrador": {
        "model": "inherit",
        "color": "blue",
        "tools": "Agent, Bash, Read, Write, Edit, Glob, Grep, Skill, TodoWrite",
    },
    "subagent-analista-requisitos": {"model": "sonnet", "color": "purple", "tools": "Bash, Read, Write, Edit, Glob, Grep, Skill"},
    "subagent-arquiteto": {"model": "opus", "color": "orange", "tools": "Bash, Read, Write, Edit, Glob, Grep, Skill"},
    "subagent-criador-tarefas": {"model": "sonnet", "color": "yellow", "tools": "Bash, Read, Write, Edit, Glob, Grep, Skill"},
    "subagent-desenvolvedor": {"model": "sonnet", "color": "green", "tools": "Bash, Read, Write, Edit, Glob, Grep, Skill"},
    "subagent-revisor-codigo": {"model": "opus", "color": "red", "tools": "Bash, Read, Write, Edit, Glob, Grep, Skill"},
    "subagent-qa": {"model": "haiku", "color": "cyan", "tools": "Bash, Read, Write, Edit, Glob, Grep, Skill"},
}

NOTA_COMUM = """
> **Adaptação para o Claude Code (harness).** Este prompt é o original da fábrica (opencode), preservado.
> Equivalências neste ambiente:
> - Agentes: `fabrica-software/<nome>` passou a ser o subagente `<nome>` do Claude Code (pasta `.claude/agents/`).
> - Skills do Spec Kit: `speckit-specify`, `speckit-plan` etc. estão instaladas pelo `specify init --ai claude`.
>   Use a ferramenta **Skill** com esse nome; se ela não existir, leia e siga o arquivo do comando
>   equivalente em `.claude/commands/` (ex.: `speckit.specify.md`), executando os scripts de `.specify/scripts/`.
> - Arquivo de contexto do agente: onde o texto diz `AGENTS.md`, neste harness é o `CLAUDE.md` da raiz.
> - Permissões: as regras de `permission` do cabeçalho original são aplicadas pelo hook
>   `.claude/hooks/fabrica_guard.py` (política em `.claude/fabrica/policy.json`). Um comando ou edição negado
>   pelo hook é uma regra da fábrica, não um erro a contornar.
> - Ao terminar, o hook `SubagentStop` registra no Slack o seu bloco de status; por isso encerre sempre com o bloco exigido.
"""

NOTA_ORQUESTRADOR = """
> **Adaptação para o Claude Code (orquestrador).**
> - Você aciona cada subagente com a ferramenta **Agent**, passando `subagent_type` igual ao nome do subagente
>   (ex.: `subagent-arquiteto`) e o handoff completo no `prompt`. Subagentes do Claude Code começam sem contexto,
>   exatamente como o handoff da fábrica pressupõe.
> - A barreira `ask` do Arquiteto continua existindo: `.claude/settings.json` exige confirmação humana para `Agent(subagent-arquiteto)`.
> - No Windows, o `gh` pode estar em `C:\\Program Files\\GitHub CLI\\gh.exe` (o próprio fluxo já prevê isso em E0).
> - Ao registrar cada etapa, você também pode citar ao humano que o Slack recebeu o status do subagente (hook `SubagentStop`).
"""


def ler_original(caminho: Path):
    texto = caminho.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", texto, re.S)
    if not m:
        raise ValueError(f"cabeçalho YAML não encontrado em {caminho}")
    cabecalho, corpo = m.group(1), m.group(2)
    desc = re.search(r"^description:\s*(.+)$", cabecalho, re.M).group(1).strip()
    return desc, cabecalho, corpo


def politica_do_cabecalho(cabecalho: str) -> dict:
    """Extrai os blocos edit/bash/task do `permission` original (YAML simples, sem dependências)."""
    politica, bloco = {}, None
    for linha in cabecalho.splitlines():
        m_bloco = re.match(r"^  (edit|bash|task):\s*$", linha)
        if m_bloco:
            bloco = m_bloco.group(1)
            politica[bloco] = []
            continue
        m_regra = re.match(r"^    (['\"])(.*)\1:\s*(allow|deny|ask)\s*$", linha)
        if bloco and m_regra:
            politica[bloco].append([m_regra.group(2), m_regra.group(3)])
        elif not linha.startswith("    "):
            bloco = None
    # Nomes dos agentes no Claude Code e arquivo de contexto do harness (CLAUDE.md no lugar de AGENTS.md).
    for regra in politica.get("task", []):
        regra[0] = regra[0].replace("fabrica-software/", "")
    if any(r[0] == "AGENTS.md" for r in politica.get("edit", [])):
        politica["edit"].append(["CLAUDE.md", "allow"])
    return politica


def ajustar_corpo(corpo: str) -> str:
    return corpo.replace("fabrica-software/subagent-", "subagent-").replace("fabrica-software/orquestrador", "orquestrador")


def main():
    origem, destino = Path(sys.argv[1]), Path(sys.argv[2])
    pasta_agentes = destino / "agents"
    pasta_agentes.mkdir(parents=True, exist_ok=True)
    politica_total = {}

    for nome, cfg in AGENTES.items():
        desc, cabecalho, corpo = ler_original(origem / f"{nome}.md")
        politica_total[nome] = politica_do_cabecalho(cabecalho)
        nota = NOTA_ORQUESTRADOR if nome == "orquestrador" else ""
        frontmatter = (
            "---\n"
            f"name: {nome}\n"
            f"description: {json.dumps(desc, ensure_ascii=False)}\n"
            f"tools: {cfg['tools']}\n"
            f"model: {cfg['model']}\n"
            f"color: {cfg['color']}\n"
            "---\n"
        )
        saida = frontmatter + NOTA_COMUM + nota + "\n" + ajustar_corpo(corpo).lstrip("\n")
        (pasta_agentes / f"{nome}.md").write_text(saida, encoding="utf-8")
        print(f"convertido: {nome}")

    pasta_fabrica = destino / "fabrica"
    pasta_fabrica.mkdir(parents=True, exist_ok=True)
    (pasta_fabrica / "policy.json").write_text(
        json.dumps(politica_total, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("política gravada: fabrica/policy.json")


if __name__ == "__main__":
    main()
