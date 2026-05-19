#!/bin/bash
# update_web.sh - Pipeline completo de FearNot
# Corre todos los agentes (macro, technical, O&G), exporta JSON,
# y publica en Vercel automaticamente.
# Los lunes ademas corre el Synthesizer (weekly convictions).

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo "============================================================"
echo "  FearNot - Pipeline de Actualizacion Diaria"
echo "  $(date '+%Y-%m-%d %H:%M')"
echo "============================================================"
echo ""

DIA_SEMANA=$(date +%u)
ES_LUNES=false
if [ "$DIA_SEMANA" -eq 1 ]; then
    ES_LUNES=true
fi

# -- 1. Verificar API keys --
echo -e "${BLUE}[1/9]${NC} Verificando API keys..."
if [ -z "$FRED_API_KEY" ] && [ ! -f ~/Desktop/macro_agent/.env ]; then
    echo -e "${RED}ERROR: Falta .env o variables de entorno${NC}"
    exit 1
fi
echo "      OK Configuracion verificada"

if [ "$ES_LUNES" = true ]; then
    echo -e "      ${PURPLE}LUNES detectado: Synthesizer correra al final${NC}"
fi

# -- 2. Ir a la carpeta de los agentes --
cd ~/Desktop/macro_agent || { echo -e "${RED}No encuentro ~/Desktop/macro_agent${NC}"; exit 1; }

# -- 3. Macro --
echo ""
echo -e "${BLUE}[2/9]${NC} Corriendo agente macro..."
python3 collector.py > /dev/null 2>&1
python3 agent.py
echo "      OK Tesis macro generada"

# -- 4. Technical --
echo ""
echo -e "${BLUE}[3/9]${NC} Corriendo agente tecnico..."
python3 technical_collector.py > /dev/null 2>&1
python3 technical_agent.py
python3 options_flow_collector.py > /dev/null 2>&1
echo "      OK Tesis tecnica generada"

# -- 5. O&G + LPG (Energy Desk) --
echo ""
echo -e "${CYAN}[4/9]${NC} ${CYAN}Corriendo Energy Desk (O&G + LPG)...${NC}"
python3 og_collector.py > /dev/null 2>&1
python3 og_news_collector.py > /dev/null 2>&1
python3 og_agent.py
echo -e "      ${CYAN}OK Energy Desk memo generado${NC}"

# -- 6. SOLO LOS LUNES: Synthesizer --
if [ "$ES_LUNES" = true ]; then
    echo ""
    echo -e "${PURPLE}[5/9]${NC} ${PURPLE}Es lunes - corriendo Synthesizer (weekly convictions)...${NC}"
    python3 synthesizer.py
    echo -e "      ${PURPLE}OK Synthesizer ejecutado${NC}"
else
    echo ""
    echo -e "${BLUE}[5/9]${NC} (Synthesizer corre solo los lunes - hoy es $(date +%A))"
fi

# -- 7. Web exporter --
echo ""
echo -e "${BLUE}[6/9]${NC} Generando web_data.json..."
python3 web_exporter.py

# -- 8. Copiar a la web --
echo ""
echo -e "${BLUE}[7/9]${NC} Copiando JSON a fearnot-web/public/..."
cp ~/Desktop/macro_agent/data/web_data.json ~/Desktop/fearnot-web/public/
echo "      OK Copiado"

# -- 9. Push a GitHub --
echo ""
echo -e "${BLUE}[8/9]${NC} Publicando a Vercel..."
cd ~/Desktop/fearnot-web

if git diff --quiet public/web_data.json && git diff --staged --quiet public/web_data.json; then
    echo -e "${YELLOW}      No hay cambios nuevos en web_data.json${NC}"
    echo "      (probablemente ya corriste el pipeline hoy)"
else
    git add public/web_data.json
    FECHA=$(date '+%Y-%m-%d %H:%M')
    if [ "$ES_LUNES" = true ]; then
        git commit -m "Update data + O&G + weekly convictions - $FECHA"
    else
        git commit -m "Update data + O&G - $FECHA"
    fi
    git push
    echo -e "${GREEN}      OK Publicado. Vercel actualiza en 30-60 segundos.${NC}"
fi

echo ""
echo "============================================================"
echo -e "${GREEN}[9/9] Pipeline completado exitosamente${NC}"
if [ "$ES_LUNES" = true ]; then
    echo -e "${PURPLE}  Las weekly convictions estan publicadas${NC}"
fi
echo -e "${CYAN}  Energy Desk memo incluido${NC}"
echo "  Visita https://fearnot-web.vercel.app en 1 minuto"
echo "============================================================"
echo ""
