FROM grafana/grafana:11.5.2

USER root

RUN find /usr/share/grafana/public -type f \
    \( -name "*.js" -o -name "*.map" -o -name "*.tsx" -o -name "*.json" -o -name "*.html" -o -name "*.txt" \) \
    -exec sed -i "s/Welcome to Grafana/智能戰情室/g" {} +

USER grafana
