#!/usr/bin/env bash
# Executa a carga dos paineis InvestSUS (scripts/carga_todas.py) e devolve o codigo de saida.
#
# Usa o .venv da raiz do projeto, grava a saida em logs/execucao_AAAAMMDD_HHMMSS.txt e apaga arquivos de logs/ com mais
# de 90 dias. Argumentos extras vao direto para carga_todas.py, ex.:
#   ./scripts/executar_carga.sh --forcar
#   ./scripts/executar_carga.sh emendas_impedimentos_tecnicos
# Codigos de saida: 0 sucesso/ignorada, 1 erro, 2 ja em execucao.
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

PY="$RAIZ/.venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "Ambiente virtual nao encontrado em $PY (veja docs/AGENDAMENTO_LINUX.md)" >&2
    exit 1
fi

mkdir -p logs
SAIDA="logs/execucao_$(date +%Y%m%d_%H%M%S).txt"

export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
"$PY" -W ignore scripts/carga_todas.py "$@" 2>&1 | tee "$SAIDA"
CODIGO=${PIPESTATUS[0]}

find logs -type f -mtime +90 -delete
exit "$CODIGO"
