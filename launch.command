#!/bin/zsh
# launch.command — Tello Drohnen-Steuerung Launcher
# Doppelklick in Finder → öffnet Terminal und zeigt dieses Menü.
#
# Voraussetzungen:
#   venv/        → Gesture / Voice / Tests  (pip install -e .)
#   tello-sim    → PyBullet-Sim             (conda env create -f environment-sim.yml)

cd "$(dirname "$0")"
exec < /dev/tty   # wire stdin to the real terminal for the lifetime of this script

# ── ANSI ──────────────────────────────────────────────────────────────────────
BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
CYAN=$'\033[0;36m'; GREEN=$'\033[0;32m'; RED=$'\033[0;31m'

# ── Helpers ───────────────────────────────────────────────────────────────────
run_venv() {
    if [[ ! -f venv/bin/activate ]]; then
        echo ""
        echo "  ${RED}Fehler:${RESET} venv nicht gefunden."
        echo "  Erstelle mit: python3 -m venv venv && source venv/bin/activate && pip install -e ."
        return 1
    fi
    source venv/bin/activate
    python "$@"
    local ret=$?
    deactivate 2>/dev/null
    return $ret
}

run_sim() {
    if ! command -v conda &>/dev/null; then
        echo ""
        echo "  ${RED}Fehler:${RESET} conda nicht gefunden."
        echo "  Installiere Miniconda und erstelle die Umgebung:"
        echo "  conda env create -f environment-sim.yml"
        return 1
    fi
    if ! conda env list 2>/dev/null | grep -q "^tello-sim"; then
        echo ""
        echo "  ${RED}Fehler:${RESET} conda-Umgebung 'tello-sim' nicht gefunden."
        echo "  Erstelle mit: conda env create -f environment-sim.yml"
        return 1
    fi
    conda run -n tello-sim python "$@"
}

pause() {
    echo ""
    printf "  ${DIM}← beliebige Taste für Menü...${RESET} "
    read -rk 1
    echo ""
}

# ── Hauptmenü ─────────────────────────────────────────────────────────────────
while true; do
    clear
    echo ""
    printf "  ${BOLD}${CYAN}╔════════════════════════════════════════════╗${RESET}\n"
    printf "  ${BOLD}${CYAN}║    TELLO DROHNEN-STEUERUNG                 ║${RESET}\n"
    printf "  ${BOLD}${CYAN}╚════════════════════════════════════════════╝${RESET}\n"
    echo ""
    printf "  ${BOLD}GESTENSTEUERUNG${RESET}\n"
    printf "  ${GREEN}1${RESET}  Gesture → ${DIM}Mock${RESET}    (kein Hardware)\n"
    printf "  ${GREEN}2${RESET}  Gesture → ${CYAN}Sim${RESET}     (PyBullet 3D-Fenster)\n"
    printf "  ${GREEN}3${RESET}  Gesture → ${RED}Drohne${RESET}  (WLAN TELLO-XXXX)\n"
    echo ""
    printf "  ${BOLD}SPRACHSTEUERUNG${RESET}\n"
    printf "  ${GREEN}4${RESET}  Voice → ${DIM}Mock${RESET}      (ENTER zum Sprechen)\n"
    printf "  ${GREEN}5${RESET}  Voice → ${CYAN}Sim${RESET}       (PyBullet 3D-Fenster)\n"
    printf "  ${GREEN}6${RESET}  Voice → ${RED}Drohne${RESET}   (WLAN TELLO-XXXX)\n"
    printf "  ${GREEN}7${RESET}  Voice → ${DIM}Mock${RESET}      (Dauerhören, Wake-Word: »Drohne«)\n"
    echo ""
    printf "  ${BOLD}SIMULATION  ${DIM}(conda: tello-sim)${RESET}\n"
    printf "  ${GREEN}8${RESET}  Würfel-Demo\n"
    printf "  ${GREEN}9${RESET}  PID-Regelungs-Labor\n"
    echo ""
    printf "  ${BOLD}TESTS & DEMO${RESET}\n"
    printf "  ${GREEN}t${RESET}  pytest    (hardware-frei, ~2 s)\n"
    printf "  ${GREEN}d${RESET}  Würfel-Demo Mock  (Textausgabe)\n"
    echo ""
    printf "  ${GREEN}q${RESET}  ${DIM}Beenden${RESET}\n"
    echo ""
    printf "  Auswahl: "
    read -rk 1 choice
    echo "$choice"

    case "${choice}" in
        1) run_venv -m tello_control.gesture.app;                            pause ;;
        2) run_sim  -m tello_control.gesture.app --sim;                      pause ;;
        3) run_venv -m tello_control.gesture.app --real;                     pause ;;
        4) run_venv -m tello_control.voice.app;                              pause ;;
        5) run_sim  -m tello_control.voice.app --sim;                        pause ;;
        6) run_venv -m tello_control.voice.app --real;                       pause ;;
        7) run_venv -m tello_control.voice.app --continuous;                 pause ;;
        8) run_sim  -m tello_control.sim.demo;                               pause ;;
        9) run_sim  -m tello_control.sim.control_lab;                        pause ;;
        t|T) run_venv -m pytest tests/ -v;                                   pause ;;
        d|D) run_venv examples/demo.py cube;                                 pause ;;
        q|Q) echo ""; echo "  Tschüss!"; echo ""; break ;;
        *) echo "  Ungültige Auswahl – bitte 1–9, t, d oder q."; sleep 1 ;;
    esac
done
