# EOD Agent - folder gata de copiat

Acest folder conține toate fișierele necesare pentru instalarea inițială a
updaterului pe un server de magazin. Agentul propriu-zis este descărcat de la
EOD Monitor și nu trebuie copiat manual.

## 1. Copiere cu Bitvise

Copiază întregul folder local:

```text
C:\Users\Stefan.PASCU\Desktop\neweod\deploy\store-bootstrap
```

în:

```text
/SmartId/agent/tmp/store-bootstrap
```

## 2. Verificare înainte de instalare

Pe server:

```sh
systemctl cat eod-agent.service
/usr/bin/python --version
/usr/bin/python -c "import requests; print(requests.__version__)"
```

Serviciul trebuie să ruleze `/SmartId/agent/agent_eod.py`.

## 3. Instalare

Înlocuiește `5002` cu Store Code-ul serverului curent:

```sh
cd /SmartId/agent/tmp/store-bootstrap
sh install.sh 5002
```

Installerul:

- validează serverul și Store Code-ul;
- detectează automat Python 2 sau Python 3 folosit de agent;
- face backup pentru agent și configurație;
- creează `agent_config.json`;
- instalează updaterul și unitățile systemd;
- descarcă versiunea activă a agentului;
- verifică dacă agentul a rămas activ;
- activează verificarea automată la 24 de ore.

Nu continua dacă Store Code-ul afișat nu corespunde serverului.

## 4. Verificare

```sh
grep AGENT_VERSION /SmartId/agent/agent_eod.py
systemctl status eod-agent.service --no-pager -l
systemctl status eod-agent-updater.timer --no-pager -l
journalctl -u eod-agent.service -n 60 --no-pager
```

Rezultatul așteptat:

```text
AGENT_VERSION = "1.8.0"
eod-agent.service: active (running)
eod-agent-updater.timer: active (waiting)
```

Installerul se oprește dacă nu găsește exact versiunea `1.8.0`. Acest lucru
protejează împotriva unui Store Code inexistent, inactiv sau configurat greșit.

## Configurație

Implicit, installerul folosește:

```text
Server: http://10.143.252.2:8000
API key: test123
```

Pentru alte valori:

```sh
EOD_SERVER_URL="https://eod.example" EOD_API_KEY="secret" sh install.sh 5002
```

Pentru o versiune activă diferită:

```sh
EOD_EXPECTED_AGENT_VERSION="1.9.0" sh install.sh 5002
```

HTTP este permis numai pentru rețeaua internă de încredere. Pentru acces în
afara rețelei interne trebuie folosit HTTPS și o cheie API rotită.
