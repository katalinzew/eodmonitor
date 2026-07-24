# Fleet rollout

Acest folder automatizează copierea bundle-ului și instalarea agentului.

Fișierele cu IP-uri și parole au sufixul `.local.*`, sunt ignorate de Git și
nu trebuie adăugate niciodată în commit.

## Cerințe

- EOD Monitor rulează la `http://127.0.0.1:8000`;
- Bitvise SSH Client este instalat;
- host key-ul fiecărui server trebuie verificat când Bitvise îl solicită;
- magazinele trebuie să fie ACTIVE în EOD Monitor.

## Verificare fără conexiuni SSH

```cmd
rollout.bat -DryRun -All
```

Verifică IP-ul și detectează SLES 12/15 din `os_info`.

## Primul val - implicit 3 magazine

```cmd
rollout.bat
```

## Un singur magazin

```cmd
rollout.bat -StoreCode 5002
```

## Toate magazinele din lista locală

Rulează numai după validarea primului val:

```cmd
rollout.bat -All
```

Rezultatele și transcriptul complet se salvează în folderul local `logs`.

Bitvise poate folosi parole prin parametrul `-pw`, însă acestea sunt păstrate
numai în fișierul local ignorat de Git. Linia de comandă poate fi vizibilă
temporar în lista de procese Windows pe durata conectării.
