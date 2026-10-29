#!/usr/bin/env bash
# Cria/atualiza o agendamento da carga dos paineis InvestSUS (FNS) em um servidor Linux.
#
# Horários (America/Sao_Paulo): 06:00 e 12:00 (não conflita com a carga FaF de 07:30/10:30/14:30). A tentativa extra é
# segura: se a carga completa do dia já deu certo, a rotina se auto-ignora (IGNORADA); se uma carga ainda estiver
# rodando, sai com código 2 (trava do banco).
#
# Uso:
#   sudo bash scripts/agendar_linux.sh                    # systemd timer (padrão; exige root)
#   sudo bash scripts/agendar_linux.sh --usuario fns      # usuário que executa a carga (padrão: quem chamou o sudo)
#        bash scripts/agendar_linux.sh --cron             # crontab do usuário atual, sem root
#   sudo bash scripts/agendar_linux.sh --remover          # remove o timer (ou, com --cron, a entrada do crontab)
#
# O script NÃO grava senha nem toca no .env: configure o .env do projeto antes (veja docs/AGENDAMENTO_LINUX.md).
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODO=systemd
REMOVER=0
USUARIO="${SUDO_USER:-$(id -un)}"
HORARIOS=(06:00 12:00)
TZ_NEGOCIO="America/Sao_Paulo"
UNIDADE=fns-paineis-carga

while [ $# -gt 0 ]; do
    case "$1" in
        --cron) MODO=cron ;;
        --systemd) MODO=systemd ;;
        --usuario) USUARIO="${2:?--usuario exige um nome}"; shift ;;
        --remover) REMOVER=1 ;;
        -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
        *) echo "Argumento desconhecido: $1 (use --help)" >&2; exit 2 ;;
    esac
    shift
done

chmod +x "$RAIZ/scripts/executar_carga.sh" "$RAIZ/scripts/agendar_linux.sh"

# ------------------------------------------------------------------ systemd
if [ "$MODO" = systemd ]; then
    [ "$(id -u)" -eq 0 ] || { echo "O modo systemd exige root: use sudo (ou --cron)." >&2; exit 1; }
    command -v systemctl >/dev/null || { echo "systemd não encontrado: use --cron." >&2; exit 1; }
    SERVICO="/etc/systemd/system/$UNIDADE.service"
    TIMER="/etc/systemd/system/$UNIDADE.timer"

    if [ "$REMOVER" -eq 1 ]; then
        systemctl disable --now "$UNIDADE.timer" 2>/dev/null || true
        rm -f "$SERVICO" "$TIMER"
        systemctl daemon-reload
        echo "Timer $UNIDADE removido."
        exit 0
    fi

    id "$USUARIO" >/dev/null 2>&1 || { echo "Usuário '$USUARIO' não existe." >&2; exit 1; }
    [ -x "$RAIZ/.venv/bin/python" ] || { echo "Ambiente virtual ausente em $RAIZ/.venv (veja docs/AGENDAMENTO_LINUX.md)." >&2; exit 1; }
    [ -f "$RAIZ/.env" ] || { echo "Arquivo $RAIZ/.env ausente: copie .env.example e preencha." >&2; exit 1; }

    cat > "$SERVICO" <<EOF
[Unit]
Description=Carga paineis InvestSUS (Qlik Engine API -> PostgreSQL stg_paineis_fns/base_fns)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$USUARIO
WorkingDirectory=$RAIZ
ExecStart=$RAIZ/scripts/executar_carga.sh
TimeoutStartSec=3h
Nice=10
# 2 = já existe carga em execução (esperado nas tentativas extras): não conta como falha da unidade
SuccessExitStatus=2
EOF

    {
        echo "[Unit]"
        echo "Description=Agenda a carga dos paineis InvestSUS (${HORARIOS[*]} $TZ_NEGOCIO)"
        echo
        echo "[Timer]"
        for h in "${HORARIOS[@]}"; do echo "OnCalendar=*-*-* $h:00 $TZ_NEGOCIO"; done
        echo "Persistent=true"
        echo
        echo "[Install]"
        echo "WantedBy=timers.target"
    } > "$TIMER"

    systemctl daemon-reload
    systemctl enable --now "$UNIDADE.timer"
    echo "Timer '$UNIDADE' ativo (${HORARIOS[*]} $TZ_NEGOCIO), executando como '$USUARIO'."
    echo "  Próximas execuções : systemctl list-timers $UNIDADE.timer"
    echo "  Disparo manual     : sudo systemctl start $UNIDADE.service"
    echo "  Logs               : journalctl -u $UNIDADE.service -n 100   (e $RAIZ/logs/)"
    exit 0
fi

# --------------------------------------------------------------------- cron
MARCA="# $UNIDADE"
# FNS_TESTE_FUSO="-0300,+0000" (negócio,servidor) só mostra as linhas do cron calculadas, sem tocar em nada
if [ "${FNS_TESTE_FUSO:-}" = "" ]; then
    command -v crontab >/dev/null || { echo "crontab não encontrado (instale o pacote 'cron')." >&2; exit 1; }
    ALVO=(crontab)
    [ "$(id -u)" -eq 0 ] && ALVO=(crontab -u "$USUARIO")
    ATUAL="$("${ALVO[@]}" -l 2>/dev/null | grep -vF "$MARCA" || true)"

    if [ "$REMOVER" -eq 1 ]; then
        printf '%s\n' "$ATUAL" | "${ALVO[@]}" -
        echo "Entrada do cron removida."
        exit 0
    fi

    [ -x "$RAIZ/.venv/bin/python" ] || { echo "Ambiente virtual ausente em $RAIZ/.venv (veja docs/AGENDAMENTO_LINUX.md)." >&2; exit 1; }
    [ -f "$RAIZ/.env" ] || { echo "Arquivo $RAIZ/.env ausente: copie .env.example e preencha." >&2; exit 1; }
    mkdir -p "$RAIZ/logs"
fi

# O cron usa o fuso do servidor (normalmente UTC): converte os horários de Brasília para o fuso local do servidor.
# (O Brasil não tem horário de verão atualmente; se o fuso do servidor tiver, os horários deslocam 1 h duas vezes por ano.)
minutos_offset() {  # "+HHMM"/"-HHMM" (formato de `date +%z`) -> minutos
    local z="$1" sinal=1
    [ "${z:0:1}" = "-" ] && sinal=-1
    echo $(( sinal * (10#${z:1:2} * 60 + 10#${z:3:2}) ))
}
# converte "HH:MM" do fuso de negócio para minutos do dia no fuso do servidor, dados os dois deslocamentos (em minutos)
converter_horario() {  # $1=HH:MM  $2=deslocamento do negócio  $3=deslocamento do servidor
    local h="${1%%:*}" m="${1##*:}"
    echo $(( (10#$h * 60 + 10#$m + $3 - $2 + 1440) % 1440 ))
}

if [ "${FNS_TESTE_FUSO:-}" = "" ]; then
    Z_NEGOCIO="$(TZ=$TZ_NEGOCIO date +%z)"
    Z_LOCAL="$(date +%z)"
    # America/Sao_Paulo nunca é +0000: se vier assim, o banco de fusos (tzdata) não está instalado no servidor
    [ "$Z_NEGOCIO" != "+0000" ] || { echo "tzdata ausente: instale com 'sudo apt install -y tzdata'." >&2; exit 1; }
else
    Z_NEGOCIO="${FNS_TESTE_FUSO%%,*}"; Z_LOCAL="${FNS_TESTE_FUSO##*,}"   # só para teste: "-0300,+0000"
fi
OFF_NEGOCIO="$(minutos_offset "$Z_NEGOCIO")"
OFF_LOCAL="$(minutos_offset "$Z_LOCAL")"

LINHAS=()
RESUMO=()
for h in "${HORARIOS[@]}"; do
    total="$(converter_horario "$h" "$OFF_NEGOCIO" "$OFF_LOCAL")"
    LINHAS+=("$((total % 60)) $((total / 60)) * * * $RAIZ/scripts/executar_carga.sh >> $RAIZ/logs/cron.log 2>&1 $MARCA")
    RESUMO+=("$(printf '%02d:%02d' $((total / 60)) $((total % 60)))")
done

if [ "${FNS_TESTE_FUSO:-}" != "" ]; then printf '%s\n' "${LINHAS[@]}"; exit 0; fi   # modo teste: só mostra as linhas

{ printf '%s\n' "$ATUAL"; printf '%s\n' "${LINHAS[@]}"; } | sed '/^$/d' | "${ALVO[@]}" -
echo "Cron instalado para '$USUARIO' (Brasília ${HORARIOS[*]} = ${RESUMO[*]} no fuso do servidor):"
printf '  %s\n' "${LINHAS[@]}"
echo "  Conferir: crontab -l   |   Log: $RAIZ/logs/cron.log"
